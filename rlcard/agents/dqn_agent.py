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

from rlcard.utils.utils import remove_illegal

Transition = namedtuple('Transition', ['state', 'action', 'reward', 'next_state', 'done', 'legal_actions'])

import torch # will use pyTorch to handle NN
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
from collections import deque
import random
from random import sample

import matplotlib
import matplotlib.pyplot as plt

from pathlib import Path
import os

######################## Your code ####################################
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
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


class DQNAgent(object):
    '''
    Approximate clone of rlcard.agents.dqn_agent.DQNAgent
    that depends on PyTorch instead of Tensorflow
    '''
    def __init__(self,
                 replay_memory_size=20000,
                 replay_memory_init_size=100,
                 update_target_estimator_every=1000,
                 discount_factor=0.99,
                 epsilon_start=1.0,
                 epsilon_end=0.1,
                 epsilon_decay_steps=20000,
                 batch_size=32,
                 num_actions=2,
                 state_shape=None,
                 train_every=1,
                 mlp_layers=None,
                 learning_rate=0.00005,
                 device=None,
                 save_path=None,
                 save_every=float('inf'),):

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
        self.use_raw = False
        self.replay_memory_init_size = replay_memory_init_size
        self.update_target_estimator_every = update_target_estimator_every
        self.discount_factor = discount_factor
        self.epsilon_decay_steps = epsilon_decay_steps
        self.batch_size = batch_size
        self.num_actions = num_actions
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
        self.q_estimator = Estimator(
            s_size=np.prod(state_shape),
            a_size=num_actions,
            learning_rate=learning_rate,
            device=self.device
        )
        self.target_estimator = deepcopy(self.q_estimator)

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

    def step(self, state):
        ''' Predict the action for genrating training data but
            have the predictions disconnected from the computation graph

        Args:
            state (numpy.array): current state

        Returns:
            action (int): an action id
        '''
        q_values = self.predict(state)
        epsilon = self.epsilons[min(self.total_t, self.epsilon_decay_steps-1)]
        legal_actions = list(state['legal_actions'].keys())
        probs = np.ones(len(legal_actions), dtype=float) * epsilon / len(legal_actions)
        best_action_idx = legal_actions.index(np.argmax(q_values))
        probs[best_action_idx] += (1.0 - epsilon)
        action_idx = np.random.choice(np.arange(len(probs)), p=probs)

        return legal_actions[action_idx]

    def eval_step(self, state):
        ''' Predict the action for evaluation purpose.

        Args:
            state (numpy.array): current state

        Returns:
            action (int): an action id
            info (dict): A dictionary containing information
        '''
        q_values = self.predict(state)
        best_action = np.argmax(q_values)

        info = {}
        info['values'] = {state['raw_legal_actions'][i]: float(q_values[list(state['legal_actions'].keys())[i]]) for i in range(len(state['legal_actions']))}

        return best_action, info

    def predict(self, state):
        ''' Predict the masked Q-values

        Args:
            state (numpy.array): current state

        Returns:
            q_values (numpy.array): a 1-d array where each entry represents a Q value
        '''
        
        q_values = self.q_estimator.predict_nograd(np.expand_dims(state['obs'], 0))[0]
        masked_q_values = -np.inf * np.ones(self.num_actions, dtype=float)
        legal_actions = list(state['legal_actions'].keys())
        masked_q_values[legal_actions] = q_values[legal_actions]

        return masked_q_values

    def train(self):
        state_batch, action_batch, reward_batch, next_state_batch, done_batch, legal_actions_batch = self.memory.sample()
    
        # Calculate best next actions using Q-network (Double DQN)
        q_values_next = self.q_estimator.predict_nograd(next_state_batch)
        best_actions = np.argmax(q_values_next, axis=1)
    
        # Evaluate best next actions using Target-network (Double DQN)
        q_values_next_target = self.target_estimator.predict_nograd(next_state_batch)
        target_batch = reward_batch + np.invert(done_batch).astype(np.float32) * \
            self.discount_factor * q_values_next_target[np.arange(self.batch_size), best_actions]
    
        # Perform gradient descent update
        state_batch = np.array(state_batch)
        loss = self.q_estimator.update(state_batch, action_batch, target_batch)
    
        print(f'\rINFO - Step {self.total_t}, rl-loss: {loss}', end='')
    
        # Update the target estimator periodically
        if self.train_t % self.update_target_estimator_every == 0:
            self.q_estimator.update_target_network()
            print("\nINFO - Copied model parameters to target network.")



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
            'agent_type': 'DQNAgent',
            'q_estimator': self.q_estimator.checkpoint_attributes(),
            'memory': self.memory.checkpoint_attributes(),
            'total_t': self.total_t,
            'train_t': self.train_t,
            'replay_memory_init_size': self.replay_memory_init_size,
            'update_target_estimator_every': self.update_target_estimator_every,
            'discount_factor': self.discount_factor,
            'epsilon_start': self.epsilons.min(),
            'epsilon_end': self.epsilons.max(),
            'epsilon_decay_steps': self.epsilon_decay_steps,
            'batch_size': self.batch_size,
            'num_actions': self.num_actions,
            'train_every': self.train_every,
            'device': self.device,
            'save_path': self.save_path,
            'save_every': self.save_every
        }

    @classmethod
    def from_checkpoint(cls, checkpoint):
        '''
        Restore the model from a checkpoint
        
        Args:
            checkpoint (dict): the checkpoint attributes generated by checkpoint_attributes()
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
                     
    def save_checkpoint(self, path, filename='checkpoint_dqn.pt'):
        ''' Save the model checkpoint (all attributes)

        Args:
            path (str): the path to save the model
            filename(str): the file name of checkpoint
        '''
        torch.save(self.checkpoint_attributes(), os.path.join(path, filename))


class Estimator:
    def __init__(self, s_size, a_size, learning_rate=0.001, device=None):
        """
        Initialize an Estimator object.
        Args:
            s_size (int): The size of the state space.
            a_size (int): The size of the action space.
            learning_rate (float): Learning rate for optimization.
            device (torch.device): The device to use (CPU or GPU).
        """
        self.device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Initialize the Q-network and target network
        self.qnet = QNetwork(s_size, a_size).to(self.device)
        self.target_qnet = TargetNetwork(s_size, a_size).to(self.device)

        # Set loss function and optimizer
        self.optimizer = torch.optim.Adam(self.qnet.parameters(), lr=learning_rate)
        self.loss_fn = nn.MSELoss()

    def predict_nograd(self, states):
        """
        Predict Q-values without tracking gradients (used for target calculation).
        Args:
            states (np.ndarray): Batch of states.
        Returns:
            np.ndarray: Predicted Q-values.
        """
        self.qnet.eval()
        with torch.no_grad():
            states_tensor = torch.tensor(states, dtype=torch.float32).to(self.device)
            q_values = self.qnet(states_tensor).cpu().numpy()
        return q_values

    def update(self, states, actions, targets):
        """
        Update the Q-network using the given targets.
        Args:
            states (np.ndarray): Batch of states.
            actions (np.ndarray): Batch of actions.
            targets (np.ndarray): Batch of target Q-values.
        Returns:
            float: Loss for the current update.
        """
        self.qnet.train()
        states_tensor = torch.tensor(states, dtype=torch.float32).to(self.device)
        actions_tensor = torch.tensor(actions, dtype=torch.int64).to(self.device)
        targets_tensor = torch.tensor(targets, dtype=torch.float32).to(self.device)

        # Compute Q-values for the given actions
        q_values = self.qnet(states_tensor)
        q_values = q_values.gather(1, actions_tensor.unsqueeze(-1)).squeeze(-1)

        # Compute loss
        loss = self.loss_fn(q_values, targets_tensor)

        # Perform optimization
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        return loss.item()

    def update_target_network(self):
        """
        Update the target network by copying weights from the Q-network.
        """
        self.target_qnet.load_state_dict(self.qnet.state_dict())

    def checkpoint_attributes(self):
        """
        Return the checkpoint attributes for saving/restoring the model.
        """
        return {
            'qnet': self.qnet.state_dict(),
            'target_qnet': self.target_qnet.state_dict(),
            'optimizer': self.optimizer.state_dict(),
        }

    @classmethod
    def from_checkpoint(cls, checkpoint, s_size, a_size, learning_rate=0.001, device=None):
        """
        Restore an Estimator object from a checkpoint.
        Args:
            checkpoint (dict): Checkpoint attributes.
            s_size (int): State size.
            a_size (int): Action size.
            learning_rate (float): Learning rate.
            device (torch.device): Device to use.
        Returns:
            Estimator: Restored Estimator object.
        """
        estimator = cls(s_size, a_size, learning_rate, device)
        estimator.qnet.load_state_dict(checkpoint['qnet'])
        estimator.target_qnet.load_state_dict(checkpoint['target_qnet'])
        estimator.optimizer.load_state_dict(checkpoint['optimizer'])
        return estimator



class EstimatorNetwork(nn.Module):
    ''' The function approximation network for Estimator
        It is just a series of tanh layers. All in/out are torch.tensor
    '''

    def __init__(self, num_actions=2, state_shape=None, mlp_layers=None):
        ''' Initialize the Q network

        Args:
            num_actions (int): number of legal actions
            state_shape (list): shape of state tensor
            mlp_layers (list): output size of each fc layer
        '''
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
        ''' Predict action values

        Args:
            s  (Tensor): (batch, state_shape)
        '''
        return self.fc_layers(s)

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
