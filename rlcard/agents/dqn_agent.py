''' DQN agent

The code is derived from https://github.com/dennybritz/reinforcement-learning/blob/master/DQN/dqn.py

Copyright (c) 2019 Matthew Judell
Copyright (c) 2019 DATA Lab at Texas A&M University
Copyright (c) 2016 Denny Britz

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.  
'''

import os 
import random
import numpy as np
import torch
import torch.nn as nn
from collections import namedtuple
from copy import deepcopy
import torch.nn.functional as F

from rlcard.utils.utils import remove_illegal
from torch.optim.optimizer import Kwargs
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

Transition = namedtuple('Transition', ['state', 'action', 'reward', 'next_state', 'done', 'legal_actions'])


class DQNAgent(object):
    '''
    Approximate clone of rlcard.agents.dqn_agent.DQNAgent
    that depends on PyTorch instead of Tensorflow
    '''
    def __init__(self,
                 state_size, #added  
                 action_size, #added 
                 replay_memory_size=20000,
                 replay_memory_init_size=100,
                 update_target_estimator_every=1000,
                 discount_factor=0.99,
                 epsilon_start=1.0,
                 epsilon_end=0.1,
                 epsilon_decay_steps=20000,
                 batch_size=32,
                 #num_actions=2,
                 #state_shape=None,
                 train_every=1,
                 #mlp_layers=None,
                 learning_rate=0.00005,
                 device=None,
                 save_path=None,
                 save_every=float('inf'),
                 **Kwargs): #added 

        '''
        Q-Learning algorithm for off-policy TD control using Function Approximation.
        Finds the optimal greedy policy while following an epsilon-greedy policy.

        Args:
            replay_memory_size (int): Size of the replay memory
            replay_memory_init_size (int): Number of random experiences to sample when initializing
              the reply memory.
            update_target_estimator_every (int): Copy parameters from the Q estimator to the
              target estimator every N steps
            discount_factor (float): Gamma discount factor
            epsilon_start (float): Chance to sample a random action when taking an action.
              Epsilon is decayed over time and this is the start value
            epsilon_end (float): The final minimum value of epsilon after decaying is done
            epsilon_decay_steps (int): Number of steps to decay epsilon over
            batch_size (int): Size of batches to sample from the replay memory
            evaluate_every (int): Evaluate every N steps
            num_actions (int): The number of the actions
            state_space (list): The space of the state vector
            train_every (int): Train the network every X steps.
            mlp_layers (list): The layer number and the dimension of each layer in MLP
            learning_rate (float): The learning rate of the DQN agent.
            device (torch.device): whether to use the cpu or gpu
            save_path (str): The path to save the model checkpoints
            save_every (int): Save the model every X training steps
        '''
        self.state_size = state_size #added 
        self.action_size = action_size #added 
        #self.use_raw = False
        self.replay_memory_init_size = replay_memory_init_size
        self.update_target_estimator_every = update_target_estimator_every
        self.discount_factor = discount_factor
        self.epsilon_decay_steps = epsilon_decay_steps
        self.batch_size = batch_size
        #self.num_actions = num_actions
        self.train_every = train_every

        # Torch device
        if device is None:
            self.device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
        else:
            self.device = device

        # Total timesteps
        self.total_t = 0

        # Total training step
        self.train_t = 0

        # The epsilon decay scheduler
        self.epsilons = np.linspace(epsilon_start, epsilon_end, epsilon_decay_steps)

        # Create estimators
        #self.q_estimator = Estimator(num_actions=num_actions, learning_rate=learning_rate, state_shape=state_shape, \
        #    mlp_layers=mlp_layers, device=self.device)
        #self.target_estimator = Estimator(num_actions=num_actions, learning_rate=learning_rate, state_shape=state_shape, \
        #    mlp_layers=mlp_layers, device=self.device)

        #adding in the Q and Target Network Initialization
        self.qnetwork = QNetwork(state_size, action_size, 64, 64, 64).to(self.device) #added 
        self.tnetwork = TargetNetwork(state_size, action_size, 64, 64, 64).to(self.device) #added 
        self.optimizer = torch.optim.RMSprop(self.qnetwork.parameters(), lr=learning_rate) #added 

        # Create replay memory
        self.memory = Memory(replay_memory_size, batch_size)
        
        # Checkpoint saving parameters
        self.save_path = save_path
        self.save_every = save_every

    def feed(self, ts):
        ''' Store data in to replay buffer and train the agent. There are two stages.
            In stage 1, populate the memory without training
            In stage 2, train the agent every several timesteps

        Args:
            ts (list): a list of 5 elements that represent the transition
        '''
        (state, action, reward, next_state, done) = tuple(ts)
        self.feed_memory(state['obs'], action, reward, next_state['obs'], list(next_state['legal_actions'].keys()), done)
        self.total_t += 1
        tmp = self.total_t - self.replay_memory_init_size
        if tmp>=0 and tmp%self.train_every == 0:
            self.train()

    def epsilon_greedy_action(self, state, epsilon):
        """
        Returns an action for the given state using the epsilon-greedy strategy.
    
        Args:
            state (array_like): current state
            epsilon (float): exploration rate
    
        Returns:
            action (int): selected action
        """
        self.qnetwork.reset_noise()
        legal_actions = list(state['legal_actions'].keys())
        print(f"Legal actions: {legal_actions}")
        with torch.no_grad():
            # Convert state to a tensor if not already
            #state_tensor = torch.tensor(state, dtype=torch.float32).unsqueeze(0).to(self.device)
            state_tensor = torch.tensor(state['obs'], dtype=torch.float32).unsqueeze(0).to(self.device)
            q_values = self.qnetwork(state_tensor).cpu().detach().numpy().squeeze()
            print(f"Q-values: {q_values} (shape: {q_values.shape})")
            print(f"Legal actions: {legal_actions}")
            
        masked_q_values = np.full_like(q_values, -np.inf)
        for action in legal_actions:
            if action < len(q_values):  # Ensure action index is valid
                masked_q_values[action] = q_values[action]
        print(f"Masked Q-values: {masked_q_values}")

        if np.random.rand() < epsilon:  # Exploration
            selected_action = np.random.choice(legal_actions)
        else:  # Exploitation
            selected_action = np.argmax(masked_q_values)
            
        assert selected_action in legal_actions, f"Selected action {selected_action} is not legal. Legal actions: {legal_actions}"

        return selected_action

    def step(self, state):
        ''' Predict the action for genrating training data but
            have the predictions disconnected from the computation graph

        Args:
            state (numpy.array): current state

        Returns:
            action (int): an action id
        
        observation = state['obs']
    
        q_values, epsilon = self.predict(observation)
        epsilon = self.epsilons[min(self.total_t, self.epsilon_decay_steps-1)]
        legal_actions = list(state['legal_actions'].keys())
        probs = np.ones(len(legal_actions), dtype=float) * epsilon / len(legal_actions)
        best_action_idx = legal_actions.index(np.argmax(q_values))
        probs[best_action_idx] += (1.0 - epsilon)
        action_idx = np.random.choice(np.arange(len(probs)), p=probs)

        return legal_actions[action_idx]
        '''
        observation = state['obs']
        epsilon = self.epsilons[min(self.total_t, self.epsilon_decay_steps - 1)]
        return self.epsilon_greedy_action(observation, epsilon)

    def eval_step(self, state):
        ''' Predict the action for evaluation purpose.

        Args:
            state (numpy.array): current state

        Returns:
            action (int): an action id
            info (dict): A dictionary containing information
        
        q_values = self.predict(state)
        best_action = np.argmax(q_values)

        info = {}
        info['values'] = {state['raw_legal_actions'][i]: float(q_values[list(state['legal_actions'].keys())[i]]) for i in range(len(state['legal_actions']))}

        return best_action, info
        '''
        observation = state['obs']
        legal_actions = list(state['legal_actions'].keys())
        #action = self.epsilon_greedy_action(observation, epsilon=0)  # Greedy policy
        with torch.no_grad():
            q_values = self.qnetwork(torch.tensor(observation, dtype=torch.float32).unsqueeze(0).to(self.device)).cpu().numpy().squeeze()
        best_action = np.argmax(q_values)
        if best_action not in legal_actions:
            best_action = np.random.choice(legal_actions)
            
        info = {
            'values': {a: float(q_values[a]) for a in legal_actions}
        }
        return best_action, info

    def predict(self, state):
        ''' Predict the masked Q-values

        Args:
            state (numpy.array): current state

        Returns:
            q_values (numpy.array): a 1-d array where each entry represents a Q value
        '''
        
        #q_values = self.q_estimator.predict_nograd(np.expand_dims(state['obs'], 0))[0]
        #masked_q_values = -np.inf * np.ones(self.num_actions, dtype=float)
        #legal_actions = list(state['legal_actions'].keys())
        #masked_q_values[legal_actions] = q_values[legal_actions]

        #return masked_q_values
        epsilon = self.epsilons[min(self.total_t, len(self.epsilons) - 1)]
        with torch.no_grad():
          state_tensor = torch.tensor(state, dtype=torch.float32).unsqueeze(0).to(self.device)
          q_values = self.qnetwork(state_tensor).cpu().numpy()[0]
        return q_values, epsilon

    def train(self):
        ''' Train the network

        Returns:
            loss (float): The loss of the current batch.
        '''
        '''
        state_batch, action_batch, reward_batch, next_state_batch, done_batch, legal_actions_batch = self.memory.sample()

        # Calculate best next actions using Q-network (Double DQN)
        q_values_next = self.q_estimator.predict_nograd(next_state_batch)
        legal_actions = []
        for b in range(self.batch_size):
            legal_actions.extend([i + b * self.num_actions for i in legal_actions_batch[b]])
        masked_q_values = -np.inf * np.ones(self.num_actions * self.batch_size, dtype=float)
        masked_q_values[legal_actions] = q_values_next.flatten()[legal_actions]
        masked_q_values = masked_q_values.reshape((self.batch_size, self.num_actions))
        best_actions = np.argmax(masked_q_values, axis=1)

        # Evaluate best next actions using Target-network (Double DQN)
        q_values_next_target = self.target_estimator.predict_nograd(next_state_batch)
        target_batch = reward_batch + np.invert(done_batch).astype(np.float32) * \
            self.discount_factor * q_values_next_target[np.arange(self.batch_size), best_actions]

        # Perform gradient descent update
        state_batch = np.array(state_batch)

        loss = self.q_estimator.update(state_batch, action_batch, target_batch)
        print('\rINFO - Step {}, rl-loss: {}'.format(self.total_t, loss), end='')

        # Update the target estimator
        if self.train_t % self.update_target_estimator_every == 0:
            self.target_estimator = deepcopy(self.q_estimator)
            print("\nINFO - Copied model parameters to target network.")

        self.train_t += 1

        if self.save_path and self.train_t % self.save_every == 0:
            # To preserve every checkpoint separately, 
            # add another argument to the function call parameterized by self.train_t
            self.save_checkpoint(self.save_path)
            print("\nINFO - Saved model checkpoint.")
        '''
        if len(self.memory) < self.replay_memory_init_size:
          return

        self.qnetwork.reset_noise()
        self.tnetwork.reset_noise()

        states, actions, rewards, next_states, dones = self.memory.sample()

        with torch.no_grad():
            next_actions = self.qnetwork(next_states).argmax(dim=1, keepdim=True)
            q_targets_next = self.tnetwork(next_states).gather(1, next_actions)
            q_targets = rewards + (self.discount_factor * q_targets_next * (1 - dones))

        q_values = self.qnetwork(states).gather(1, actions)

        loss = F.mse_loss(q_values, q_targets)

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        if self.total_t % self.update_target_estimator_every == 0:
            self.tnetwork.load_state_dict(self.qnetwork.state_dict())


    def feed_memory(self, state, action, reward, next_state, legal_actions, done):
        ''' Feed transition to memory

        Args:
            state (numpy.array): the current state
            action (int): the performed action ID
            reward (float): the reward received
            next_state (numpy.array): the next state after performing the action
            legal_actions (list): the legal actions of the next state
            done (boolean): whether the episode is finished
        '''
        self.memory.save(state, action, reward, next_state, legal_actions, done)

    def set_device(self, device):
        self.device = device
        self.q_estimator.device = device
        self.target_estimator.device = device

    def checkpoint_attributes(self):
        '''
        Return the current checkpoint attributes (dict)
        Checkpoint attributes are used to save and restore the model in the middle of training
        Saves the model state dict, optimizer state dict, and all other instance variables
        '''
        
        return {
            #'agent_type': 'DQNAgent',
            #'q_estimator': self.q_estimator.checkpoint_attributes(),
            #'memory': self.memory.checkpoint_attributes(),
            #'total_t': self.total_t,
            #'train_t': self.train_t,
            #'replay_memory_init_size': self.replay_memory_init_size,
            #'update_target_estimator_every': self.update_target_estimator_every,
            #'discount_factor': self.discount_factor,
            #'epsilon_start': self.epsilons.min(),
            #'epsilon_end': self.epsilons.max(),
            #'epsilon_decay_steps': self.epsilon_decay_steps,
            #'batch_size': self.batch_size,
            #'num_actions': self.num_actions,
            #'train_every': self.train_every,
            #'device': self.device,
            #'save_path': self.save_path,
            #'save_every': self.save_every
            'qnetwork_state_dict': self.qnetwork.state_dict(),
            'tnetwork_state_dict': self.tnetwork.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'memory': self.memory.checkpoint_attributes(),
            'total_t': self.total_t,
            'train_t': self.train_t,
            'epsilon_decay': self.epsilons
        }

    @classmethod
    def from_checkpoint(cls, checkpoint, state_size, action_size):
        '''
        
        print("\nINFO - Restoring model from checkpoint...")
        agent_instance = cls(
            replay_memory_size=checkpoint['memory']['memory_size'],
            replay_memory_init_size=checkpoint['replay_memory_init_size'],
            update_target_estimator_every=checkpoint['update_target_estimator_every'],
            discount_factor=checkpoint['discount_factor'],
            epsilon_start=checkpoint['epsilon_start'],
            epsilon_end=checkpoint['epsilon_end'],
            epsilon_decay_steps=checkpoint['epsilon_decay_steps'],
            batch_size=checkpoint['batch_size'],
            num_actions=checkpoint['num_actions'], 
            state_shape=checkpoint['q_estimator']['state_shape'],
            train_every=checkpoint['train_every'],
            mlp_layers=checkpoint['q_estimator']['mlp_layers'],
            learning_rate=checkpoint['q_estimator']['learning_rate'],
            device=checkpoint['device'],
            save_path=checkpoint['save_path'],
            save_every=checkpoint['save_every'],
        )
        
        agent_instance.total_t = checkpoint['total_t']
        agent_instance.train_t = checkpoint['train_t']
        
        agent_instance.q_estimator = Estimator.from_checkpoint(checkpoint['q_estimator'])
        agent_instance.target_estimator = deepcopy(agent_instance.q_estimator)
        agent_instance.memory = Memory.from_checkpoint(checkpoint['memory'])

        return agent_instance
        '''
        agent = cls(state_size, action_size)
        agent.qnetwork.load_state_dict(checkpoint['qnetwork_state_dict'])
        agent.tnetwork.load_state_dict(checkpoint['tnetwork_state_dict'])
        agent.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        agent.memory = Memory.from_checkpoint(checkpoint['memory'])
        agent.total_t = checkpoint['total_t']
        agent.train_t = checkpoint['train_t']
        agent.epsilons = checkpoint['epsilon_decay']
        return agent

    def save_checkpoint(self, path, filename='checkpoint_dqn.pt'):
        ''' Save the model checkpoint (all attributes)

        Args:
            path (str): the path to save the model
            filename(str): the file name of checkpoint
        '''
        torch.save(self.checkpoint_attributes(), os.path.join(path, filename))

'''
class Estimator(object):
    

    def __init__(self, num_actions=2, learning_rate=0.001, state_shape=None, mlp_layers=None, device=None):
        
        self.num_actions = num_actions
        self.learning_rate=learning_rate
        self.state_shape = state_shape
        self.mlp_layers = mlp_layers
        self.device = device

        # set up Q model and place it in eval mode
        qnet = EstimatorNetwork(num_actions, state_shape, mlp_layers)
        qnet = qnet.to(self.device)
        self.qnet = qnet
        self.qnet.eval()

        # initialize the weights using Xavier init
        for p in self.qnet.parameters():
            if len(p.data.shape) > 1:
                nn.init.xavier_uniform_(p.data)

        # set up loss function
        self.mse_loss = nn.MSELoss(reduction='mean')

        # set up optimizer
        self.optimizer =  torch.optim.Adam(self.qnet.parameters(), lr=self.learning_rate)

    def predict_nograd(self, s):
      
        with torch.no_grad():
            s = torch.from_numpy(s).float().to(self.device)
            q_as = self.qnet(s).cpu().numpy()
        return q_as

    def update(self, s, a, y):
        
        self.optimizer.zero_grad()

        self.qnet.train()

        s = torch.from_numpy(s).float().to(self.device)
        a = torch.from_numpy(a).long().to(self.device)
        y = torch.from_numpy(y).float().to(self.device)

        # (batch, state_shape) -> (batch, num_actions)
        q_as = self.qnet(s)

        # (batch, num_actions) -> (batch, )
        Q = torch.gather(q_as, dim=-1, index=a.unsqueeze(-1)).squeeze(-1)

        # update model
        batch_loss = self.mse_loss(Q, y)
        batch_loss.backward()
        self.optimizer.step()
        batch_loss = batch_loss.item()

        self.qnet.eval()

        return batch_loss
    
    def checkpoint_attributes(self):
       
        return {
            'qnet': self.qnet.state_dict(),
            'optimizer': self.optimizer.state_dict(),
            'num_actions': self.num_actions,
            'learning_rate': self.learning_rate,
            'state_shape': self.state_shape,
            'mlp_layers': self.mlp_layers,
            'device': self.device
        }
        
    @classmethod
    def from_checkpoint(cls, checkpoint):
        
        estimator = cls(
            num_actions=checkpoint['num_actions'],
            learning_rate=checkpoint['learning_rate'],
            state_shape=checkpoint['state_shape'],
            mlp_layers=checkpoint['mlp_layers'],
            device=checkpoint['device']
        )
        
        estimator.qnet.load_state_dict(checkpoint['qnet'])
        estimator.optimizer.load_state_dict(checkpoint['optimizer'])
        return estimator
'''
'''
class EstimatorNetwork(nn.Module):
  

    def __init__(self, num_actions=2, state_shape=None, mlp_layers=None):
       
        super(EstimatorNetwork, self).__init__()

        self.num_actions = num_actions
        self.state_shape = state_shape
        self.mlp_layers = mlp_layers

        # build the Q network
        layer_dims = [np.prod(self.state_shape)] + self.mlp_layers
        fc = [nn.Flatten()]
        fc.append(nn.BatchNorm1d(layer_dims[0]))
        for i in range(len(layer_dims)-1):
            fc.append(nn.Linear(layer_dims[i], layer_dims[i+1], bias=True))
            fc.append(nn.Tanh())
        fc.append(nn.Linear(layer_dims[-1], self.num_actions, bias=True))
        self.fc_layers = nn.Sequential(*fc)

    def forward(self, s):
       
        return self.fc_layers(s)

'''
#adding in the noisy DQN code with Qnetwork and Target Network 
class NoisyLinear(nn.Module):
    def __init__(self, in_features, out_features, sigma_init=0.5):
        super(NoisyLinear, self).__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.sigma_init = sigma_init

        # Learnable parameters
        self.weight_mu = nn.Parameter(torch.empty(out_features, in_features))
        self.weight_sigma = nn.Parameter(torch.empty(out_features, in_features))
        self.bias_mu = nn.Parameter(torch.empty(out_features))
        self.bias_sigma = nn.Parameter(torch.empty(out_features))

        # Fixed noise parameters
        self.register_buffer("weight_epsilon", torch.empty(out_features, in_features))
        self.register_buffer("bias_epsilon", torch.empty(out_features))

        # Initialization
        self.reset_parameters()
        self.reset_noise()

    def reset_parameters(self):
        bound = 1 / np.sqrt(self.in_features)
        self.weight_mu.data.uniform_(-bound, bound)
        self.bias_mu.data.uniform_(-bound, bound)
        self.weight_sigma.data.fill_(self.sigma_init / np.sqrt(self.in_features))
        self.bias_sigma.data.fill_(self.sigma_init / np.sqrt(self.out_features))

    def reset_noise(self):
        self.weight_epsilon.normal_()
        self.bias_epsilon.normal_()
    def forward(self, x):
        if self.training:
            weight = self.weight_mu + self.weight_sigma * self.weight_epsilon
            bias = self.bias_mu + self.bias_sigma * self.bias_epsilon
        return F.linear(x, weight, bias)

# Simple NN with two hidden layers
class QNetwork(nn.Module):
    def __init__(self, s_size,  a_size, fc1_units=64, fc2_units=64, fc3_units=64):
    #def __init__(self, s_size,  a_size, fc1_units=256, fc2_units=128):
        super(QNetwork, self).__init__()
        self.fc1 = nn.Linear(s_size, fc1_units)
        self.fc2 = NoisyLinear(fc1_units, fc2_units)
        self.fc3 = NoisyLinear(fc2_units, fc3_units)
        self.value_layer = NoisyLinear(fc3_units, 1)
        self.advantage_layer = NoisyLinear(fc3_units, a_size)
        #self.fc3 = nn.Linear(fc2_units, fc3_units)
        #self.fc4 = nn.Linear(fc3_units, a_size)
    def forward(self, state):
        """Perform forward propagation."""

        x = state
        if not isinstance(x, torch.Tensor):
            x = torch.tensor(x,
                             device=device,
                             dtype=torch.float32)
            x = x.unsqueeze(0)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = F.relu(self.fc3(x))
        value = self.value_layer(x)
        advantage = self.advantage_layer(x)
        q_values = value + (advantage - advantage.mean(dim=1, keepdim=True))
        return q_values

        #x = self.fc4(x)
        #x = self.fc3(x)



    def reset_noise(self):
        self.value_layer.reset_noise()
        self.advantage_layer.reset_noise()

class TargetNetwork(nn.Module):
    def __init__(self, s_size,  a_size, fc1_units=64, fc2_units=64, fc3_units=64):
    #def __init__(self, s_size,  a_size, fc1_units=256, fc2_units=128):
        super(TargetNetwork, self).__init__()
        self.fc1 = nn.Linear(s_size, fc1_units)
        self.fc2 = NoisyLinear(fc1_units, fc2_units)
        self.fc3 = NoisyLinear(fc2_units, fc3_units)
        self.value_layer = NoisyLinear(fc3_units, 1)
        self.advantage_layer = NoisyLinear(fc3_units, a_size)
        #self.fc3 = nn.Linear(fc2_units, fc3_units)
        #self.fc4 = nn.Linear(fc3_units, a_size)

    def forward(self, state):
        """Perform forward propagation."""

        x = state
        if not isinstance(x, torch.Tensor):
            x = torch.tensor(x,
                             device=device,
                             dtype=torch.float32)
            x = x.unsqueeze(0)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = F.relu(self.fc3(x))
        #x = self.fc4(x)
        #x = self.fc3(x)
        value = self.value_layer(x)
        advantage = self.advantage_layer(x)
        q_values = value + (advantage - advantage.mean(dim=1, keepdim=True))
        return q_values


    def reset_noise(self):
        self.value_layer.reset_noise()
        self.advantage_layer.reset_noise()


class Memory(object):
    ''' Memory for saving transitions
    '''

    def __init__(self, memory_size, batch_size):
        ''' Initialize
        Args:
            memory_size (int): the size of the memroy buffer
        '''
        self.memory_size = memory_size
        self.batch_size = batch_size
        self.memory = []

    def save(self, state, action, reward, next_state, legal_actions, done):
        ''' Save transition into memory

        Args:
            state (numpy.array): the current state
            action (int): the performed action ID
            reward (float): the reward received
            next_state (numpy.array): the next state after performing the action
            legal_actions (list): the legal actions of the next state
            done (boolean): whether the episode is finished
        '''
        if len(self.memory) == self.memory_size:
            self.memory.pop(0)
        transition = Transition(state, action, reward, next_state, done, legal_actions)
        self.memory.append(transition)

    def sample(self):
        ''' Sample a minibatch from the replay memory

        Returns:
            state_batch (list): a batch of states
            action_batch (list): a batch of actions
            reward_batch (list): a batch of rewards
            next_state_batch (list): a batch of states
            done_batch (list): a batch of dones
        '''
        samples = random.sample(self.memory, self.batch_size)
        samples = tuple(zip(*samples))
        return tuple(map(np.array, samples[:-1])) + (samples[-1],)

    def checkpoint_attributes(self):
        ''' Returns the attributes that need to be checkpointed
        '''
        
        return {
            'memory_size': self.memory_size,
            'batch_size': self.batch_size,
            'memory': self.memory
        }
            
    @classmethod
    def from_checkpoint(cls, checkpoint):
        ''' 
        Restores the attributes from the checkpoint
        
        Args:
            checkpoint (dict): the checkpoint dictionary
            
        Returns:
            instance (Memory): the restored instance
        '''
        
        instance = cls(checkpoint['memory_size'], checkpoint['batch_size'])
        instance.memory = checkpoint['memory']
        return instance
    '''added len memory to get current size of memory'''
    def __len__(self):
        ''' Return the current size of the memory '''
        return len(self.memory)
    

