""" 
Based on PureJaxRL Implementation of PPO
"""

import os
import jax
import jax.numpy as jnp
import flax.linen as nn
import numpy as np
import optax
from flax.linen.initializers import constant, orthogonal
from typing import Sequence, NamedTuple, Any
from flax.training.train_state import TrainState
import distrax
import jaxmarl
from jaxmarl.wrappers.baselines import LogWrapper
import matplotlib.pyplot as plt
import hydra
from omegaconf import OmegaConf
import wandb
# import orbax.checkpoint
from flax.training import checkpoints
from safetensors.flax import save_file
from flax.traverse_util import flatten_dict
from typing import NamedTuple, Dict, Union
import orbax.checkpoint
from flax.training import orbax_utils
import chex
from flax.traverse_util import flatten_dict, unflatten_dict
from safetensors.flax import save_file, load_file
import pandas as pd
import seaborn as sns
from flax.training import checkpoints
from safetensors.flax import save_file
from flax.traverse_util import flatten_dict
from typing import NamedTuple, Dict, Union
from jaxmarl.environments import SimpleFacmacMPE
from jaxmarl.environments.mpe.simple import State, SimpleMPE
from functools import partial
import chex
from flax.traverse_util import flatten_dict, unflatten_dict
from safetensors.flax import save_file, load_file

class ActorCritic(nn.Module):
    action_dim: Sequence[int]
    activation: str = "tanh"

    @nn.compact
    def __call__(self, x):
        if self.activation == "relu":
            activation = nn.relu
        else:
            activation = nn.tanh
        actor_mean = nn.Dense(
            128, kernel_init=orthogonal(np.sqrt(2)), bias_init=constant(0.0)
        )(x)
        actor_mean = activation(actor_mean)
        actor_mean = nn.Dense(
            128, kernel_init=orthogonal(np.sqrt(2)), bias_init=constant(0.0)
        )(x)
        actor_mean = activation(actor_mean)
        actor_mean = nn.Dense(
            128, kernel_init=orthogonal(np.sqrt(2)), bias_init=constant(0.0)
        )(x)
        actor_mean = activation(actor_mean)
        actor_mean = nn.Dense(
            128, kernel_init=orthogonal(np.sqrt(2)), bias_init=constant(0.0)
        )(x)
        actor_mean = activation(actor_mean)
        actor_mean = nn.Dense(
            128, kernel_init=orthogonal(np.sqrt(2)), bias_init=constant(0.0)
        )(x)
        actor_mean = activation(actor_mean)
        actor_mean = nn.Dense(
            128, kernel_init=orthogonal(np.sqrt(2)), bias_init=constant(0.0)
        )(x)
        actor_mean = activation(actor_mean)
        actor_mean = nn.Dense(
            128, kernel_init=orthogonal(np.sqrt(2)), bias_init=constant(0.0)
        )(actor_mean)
        actor_mean = activation(actor_mean)
        actor_mean = nn.Dense(
            self.action_dim, kernel_init=orthogonal(0.01), bias_init=constant(0.0)
        )(actor_mean)
        actor_logtstd = self.param('log_std', nn.initializers.zeros, (self.action_dim,))
        pi = distrax.MultivariateNormalDiag(actor_mean, jnp.exp(actor_logtstd))

        critic = nn.Dense(
            128, kernel_init=orthogonal(np.sqrt(2)), bias_init=constant(0.0)
        )(x)
        critic = activation(critic)
        critic = nn.Dense(
            128, kernel_init=orthogonal(np.sqrt(2)), bias_init=constant(0.0)
        )(critic)
        critic = activation(critic)
        critic = nn.Dense(
            128, kernel_init=orthogonal(np.sqrt(2)), bias_init=constant(0.0)
        )(critic)
        critic = activation(critic)
        critic = nn.Dense(
            128, kernel_init=orthogonal(np.sqrt(2)), bias_init=constant(0.0)
        )(critic)
        critic = activation(critic)
        critic = nn.Dense(
            128, kernel_init=orthogonal(np.sqrt(2)), bias_init=constant(0.0)
        )(critic)
        critic = activation(critic)
        critic = nn.Dense(
            128, kernel_init=orthogonal(np.sqrt(2)), bias_init=constant(0.0)
        )(x)
        critic = activation(critic)
        critic = nn.Dense(
            128, kernel_init=orthogonal(np.sqrt(2)), bias_init=constant(0.0)
        )(x)
        critic = activation(critic)
        critic = nn.Dense(1, kernel_init=orthogonal(1.0), bias_init=constant(0.0))(
            critic
        )

        return pi, jnp.squeeze(critic, axis=-1)



class Transition(NamedTuple):
    done: jnp.ndarray
    action: jnp.ndarray
    value: jnp.ndarray
    reward: jnp.ndarray
    log_prob: jnp.ndarray
    obs: jnp.ndarray
    info: jnp.ndarray

class MultiFacmacMPE(SimpleFacmacMPE):
    """Log the episode returns and lengths.
    NOTE for now for envs where agents terminate at the same time.
    """

    def __init__(
        self,
        num_good_agents=1,
        num_adversaries=3,
        num_landmarks=2,
        view_radius=1.5,  # set -1 to deactivate
        score_function="sum"
    ):
        super().__init__( 
        num_good_agents,
        num_adversaries,
        num_landmarks,
        view_radius, 
        score_function)
        
    def rewards(self, state: State) -> Dict[str, float]:
        @partial(jax.vmap, in_axes=(0, None))
        def _collisions(agent_idx: int, other_idx: int):
            return jax.vmap(self.is_collision, in_axes=(None, 0, None))(
                agent_idx,
                other_idx,
                state,
            )

        c = _collisions(
            jnp.arange(self.num_good_agents) + self.num_adversaries,
            jnp.arange(self.num_adversaries),
        )  # [agent, adversary, collison]

        def _good(aidx: int, collisions: chex.Array):
            rew = -10 * jnp.sum(collisions[aidx])

            mr = jnp.sum(self.map_bounds_reward(jnp.abs(state.p_pos[aidx])))
            rew -= mr
            return rew

        # ad_rew = 10 * jnp.sum(c)
        
        def _adv(aidx: int, collisions: chex.Array):
            rew = 10 * jnp.sum(collisions[:,aidx])
            
            return rew

        rew = {a: _adv(i, c)
                for i, a in enumerate(self.adversaries)}
        
        rew.update(
            {
                a: _good(i + self.num_adversaries, c)
                for i, a in enumerate(self.good_agents)
            }
        )
        # print("rewards!", rew)
        return rew
    
def batchify(x: dict, agent_list, num_actors):
    max_dim = max([x[a].shape[-1] for a in agent_list])
    def pad(z, length):
        return jnp.concatenate([z, jnp.zeros(z.shape[:-1] + [length - z.shape[-1]])], -1)

    x = jnp.stack([x[a] if x[a].shape[-1] == max_dim else pad(x[a]) for a in agent_list])
    return x


def unbatchify(x: jnp.ndarray, agent_list, num_envs, num_actors):
    x = x.reshape((num_actors, num_envs, -1))
    return {a: x[i] for i, a in enumerate(agent_list)}

def flatten_agents(x):
    # print("FLATTEN SHAPE", x.shape)
    return x.reshape((x.shape[0]*x.shape[1], ))

def make_train(config, path0, path1):
    env = MultiFacmacMPE(**config["ENV_KWARGS"])
    config["NUM_ACTORS"] = env.num_agents * config["NUM_ENVS"]
    config["NUM_UPDATES"] = (
            1
    )
    # env = FlattenObservationWrapper(env) # NOTE need a batchify wrapper
    env = LogWrapper(env, replace_info=True)

    def linear_schedule(count):
        frac = 1.0 - (count // (config["NUM_MINIBATCHES"] * config["UPDATE_EPOCHS"])) / config["NUM_UPDATES"]
        return config["LR"] * frac

    def train(rng):

        # INIT NETWORK
        # TODO doesn't work for non-homogenous agents
        # print(env.action_space(env.agents[0]).shape[0])
        network0 = ActorCritic(env.action_space(env.agents[0]).shape[0], activation=config["ACTIVATION"])
        network1 = ActorCritic(env.action_space(env.agents[0]).shape[0], activation=config["ACTIVATION"])
        rng, _rng0, _rng1 = jax.random.split(rng, num=3)
        # print("randoms", _rng0, _rng1)
        # print(env.observation_space(env.agents[0]).shape)
        # print(env.agents)
        # # init_x = jnp.zeros(env.observation_space(env.agents[0]).shape)
        # print("init x", init_x)
        
        def load_params(filename):
            flattened_dict = load_file(filename)
            return unflatten_dict(flattened_dict, sep=',')
        
        network_params0 = load_params(path0)
        network_params1 = load_params(path1)
        # network_params0 = network0.init(_rng0, init_x)
        # network_params1 = network1.init(_rng1, init_x)
        if config["ANNEAL_LR"]:
            tx = optax.chain(
                optax.clip_by_global_norm(config["MAX_GRAD_NORM"]),
                optax.adam(learning_rate=linear_schedule, eps=1e-5),
            )
        else:
            tx = optax.chain(optax.clip_by_global_norm(config["MAX_GRAD_NORM"]), optax.adam(config["LR"], eps=1e-5))

        train_state0 = TrainState.create(
            apply_fn=network0.apply,
            params=network_params0,
            tx=tx,
        )
        train_state1 = TrainState.create(
            apply_fn=network1.apply,
            params=network_params1,
            tx=tx,
        )

        # INIT ENV
        rng, _rng = jax.random.split(rng)
        reset_rng = jax.random.split(_rng, config["NUM_ENVS"])
        obsv, env_state = jax.vmap(env.reset)(reset_rng)

        # TRAIN LOOP
        def _update_step(runner_state, unused):
            # COLLECT TRAJECTORIES
            def _env_step(runner_state, unused):
                train_state0, train_state1, env_state, last_obs, rng = runner_state

                obs_batch = batchify(last_obs, env.agents, config["NUM_ACTORS"])
                # print("obs_batch", obs_batch.shape)
                # print("obs_batch values", obs_batch)

                # SELECT ACTION
                rng, _rng0, _rng1 = jax.random.split(rng, num=3)

                pi0, value0 = network0.apply(train_state0.params, obs_batch[0:1].reshape((obs_batch[0:1].shape[0]*obs_batch[0:1].shape[1], -1)))
                pi1, value1 = network1.apply(train_state1.params, obs_batch[1:env.num_adversaries].reshape((obs_batch[1:env.num_adversaries].shape[0]*obs_batch[1:env.num_adversaries].shape[1], -1)))
                # print("value", value0, value1)
                action0 = pi0.sample(seed=_rng0)
                action1 = pi1.sample(seed=_rng1)
                # print("action", action0, action1)
                action = jnp.concatenate([action0, action1], axis=0)
                for _ in range(env.num_good_agents):
                    action = jnp.concatenate([action, jnp.zeros(action0.shape)], axis=0)
                # print("action", action.shape)
                log_prob0 = pi0.log_prob(action0)
                log_prob1 = pi1.log_prob(action1)
                
                env_act = unbatchify(action, env.agents, config["NUM_ENVS"], env.num_agents)
                # print("env_act", env_act)
                # STEP ENV
                rng, _rng = jax.random.split(rng)
                rng_step = jax.random.split(_rng, config["NUM_ENVS"])
                obsv, env_state, reward, done, info = jax.vmap(env.step)(
                    rng_step, env_state, env_act,
                )
                # print("info before", info)
                # info = jax.tree_map(lambda x: x[:,:env.num_adversaries].reshape((config["NUM_ADVERSARIES"])), info)
                # print("info after", info)
                # print("SHAPE CHECK", batchify(done, env.agents, config["NUM_ACTORS"]).squeeze()[0].shape, action0.shape, value0.shape, batchify(reward, env.agents, config["NUM_ACTORS"]).squeeze()[0].shape, log_prob0.shape, obs_batch[0].shape, jax.tree_map(lambda x: x[:,0], info))
                transition0 = Transition(
                    batchify(done, env.agents, config["NUM_ACTORS"]).squeeze()[0],
                    action0,
                    value0,
                    batchify(reward, env.agents, config["NUM_ACTORS"]).squeeze()[0],
                    log_prob0,
                    obs_batch[0:1].reshape((obs_batch[0:1].shape[0]*obs_batch[0:1].shape[1], -1)),
                    jax.tree_map(lambda x: x[:,0], info),
                )
                transition1 = Transition(
                    flatten_agents(batchify(done, env.agents, config["NUM_ACTORS"]).squeeze()[1:env.num_adversaries]),
                    action1,
                    value1,
                    flatten_agents(batchify(reward, env.agents, config["NUM_ACTORS"]).squeeze()[1:env.num_adversaries]),
                    log_prob1,
                    obs_batch[1:env.num_adversaries].reshape((obs_batch[1:env.num_adversaries].shape[0]*obs_batch[1:env.num_adversaries].shape[1], -1)),
                    jax.tree_map(lambda x: flatten_agents(x[:,1:env.num_adversaries]), info),
                )
                runner_state = (train_state0, train_state1, env_state, obsv, rng)
                return runner_state, (transition0, transition1)
            
            runner_state, (traj_batch0, traj_batch1) = jax.lax.scan(
                _env_step, runner_state, None, config["NUM_STEPS"]
            )
            
            train_state0, train_state1, env_state, last_obs, rng = runner_state
            
            def callback(metric):
                wandb.log(
                    metric
                )

            update_state = (train_state0, train_state1, traj_batch0, traj_batch1, rng)

            train_state0 = update_state[0]
            train_state1 = update_state[1]
            metric0 = traj_batch0.info
            metric1 = traj_batch1.info
            rng = update_state[-1]

            # r0 = {"ratio0": loss_info0["ratio"][0,0].mean()}
            # jax.debug.print('ratio0 {x}', x=r0["ratio0"])
            # loss_info0 = jax.tree_map(lambda x: x.mean(), loss_info0)
            # loss_info1 = jax.tree_map(lambda x: x.mean(), loss_info1)
            # metric0 = jax.tree_map(lambda x: x.mean(), metric0)
            # metric1 = jax.tree_map(lambda x: x.mean(), metric1)
            metric = {"agent0":{**metric0}, "agent1":{**metric1}}
            jax.experimental.io_callback(callback, None, metric)
            runner_state = (train_state0, train_state1, env_state, last_obs, rng)
            return runner_state, metric

        rng, _rng = jax.random.split(rng)
        runner_state = (train_state0, train_state1, env_state, obsv, _rng)
        runner_state, metric = jax.lax.scan(
            _update_step, runner_state, None, config["NUM_UPDATES"]
        )
        return {"runner_state": runner_state, "metrics": metric}

    return train

@hydra.main(version_base=None, config_path="config", config_name="ippo_ff_mpe_facmac")
def main(config):
    config = OmegaConf.to_container(config)

    wandb.init(
        entity=config["ENTITY"],
        project=config["PROJECT"],
        name=config["NAME"],
        tags=["IPPO", "FF"],
        config=config,
        mode=config["WANDB_MODE"],
    )
    
    pi_s = "ckpt/MPE_simple_facmac_v1/selfish/IPPO.safetensors"
    br_pi_s = "ckpt/MPE_simple_facmac_v1/br-selfish/IPPO.safetensors"
    pi_p = "ckpt/MPE_simple_facmac_v1/prosocial/IPPO.safetensors"
    br_pi_p = "ckpt/MPE_simple_facmac_v1/br-prosocial/IPPO.safetensors"
    
    
    # C(pi_s, pi_s)
    rng = jax.random.PRNGKey(config["SEED"])
    rngs = jax.random.split(rng, config["NUM_SEEDS"])
    train_jit_actual = jax.jit(make_train(config, pi_s, pi_s))
    train_jit_br = jax.jit(make_train(config, br_pi_s, pi_s))
    out_actual = jax.vmap(train_jit_actual)(rngs)
    out_br = jax.vmap(train_jit_br)(rngs)
    agent0_actual = out_actual["metrics"]["agent0"]["episode_returns"][:,:,-2,:]
    agent1_actual = out_actual["metrics"]["agent1"]["episode_returns"][:,:,-2,:]
    agent1_actual = agent1_actual.reshape((agent1_actual.shape[0], agent1_actual.shape[1], config["NUM_ENVS"], -1))
    agent1_actual = jnp.sum(agent1_actual, axis=3)
    agent0_br = out_br["metrics"]["agent0"]["episode_returns"][:,:,-2,:]
    agent1_br = out_br["metrics"]["agent1"]["episode_returns"][:,:,-2,:]
    agent1_br = agent1_br.reshape((agent1_br.shape[0], agent1_br.shape[1], config["NUM_ENVS"], -1))
    agent1_br = jnp.sum(agent1_br, axis=3)
    w_actual = agent0_actual.mean()+agent1_actual.mean()
    w_br = agent0_br.mean() + agent1_br.mean()
    c_s_s = w_actual - w_br
    print(len(jnp.ravel(agent0_actual+agent1_actual).tolist()))
    df_eval = pd.DataFrame({'context': ['pi_s']*160,
                'eval': ['pi_s']*160,
            'return': jnp.ravel(agent0_actual+agent1_actual).tolist()})
    
    df_br = pd.DataFrame({'context': ['pi_s']*160,
            'eval': ['best_response'] * 160,
            'return':jnp.ravel(agent0_br+agent1_br).tolist()})
    
    df1 = pd.concat([df_eval, df_br]).reset_index(drop=True)
    df1.to_csv('results/test.csv')
 
    print("Actual Outcome", w_actual)
    print("Selfish Outcome", w_br)
    print("C(pi_s, pi_s)", c_s_s)
    
    # C(pi_p, pi_s)
    rng = jax.random.PRNGKey(config["SEED"])
    rngs = jax.random.split(rng, config["NUM_SEEDS"])
    train_jit_actual = jax.jit(make_train(config, pi_p, pi_s))
    train_jit_br = jax.jit(make_train(config, br_pi_s, pi_s))
    out_actual = jax.vmap(train_jit_actual)(rngs)
    out_br = jax.vmap(train_jit_br)(rngs)
    agent0_actual = out_actual["metrics"]["agent0"]["episode_returns"][:,:,-2,:]
    agent1_actual = out_actual["metrics"]["agent1"]["episode_returns"][:,:,-2,:]
    agent1_actual = agent1_actual.reshape((agent1_actual.shape[0], agent1_actual.shape[1], config["NUM_ENVS"], -1))
    agent1_actual = jnp.sum(agent1_actual, axis=3)
    agent0_br = out_br["metrics"]["agent0"]["episode_returns"][:,:,-2,:]
    agent1_br = out_br["metrics"]["agent1"]["episode_returns"][:,:,-2,:]
    agent1_br = agent1_br.reshape((agent1_br.shape[0], agent1_br.shape[1], config["NUM_ENVS"], -1))
    agent1_br = jnp.sum(agent1_br, axis=3)
    w_actual = agent0_actual.mean()+agent1_actual.mean()
    w_br = agent0_br.mean() + agent1_br.mean()
    c_p_s = w_actual - w_br
    print("Actual Outcome", w_actual)
    print("Selfish Outcome", w_br)
    print("C(pi_p, pi_s)", c_p_s)
    
    df_eval = pd.DataFrame({'context': ['pi_s']*160,
                'eval': ['pi_p']*160,
            'return': jnp.ravel(agent0_actual+agent1_actual).tolist()})
    
    df2 = pd.concat([df_eval]).reset_index(drop=True)
 
    # C(pi_s, pi_p)
    rng = jax.random.PRNGKey(config["SEED"])
    rngs = jax.random.split(rng, config["NUM_SEEDS"])
    train_jit_actual = jax.jit(make_train(config, pi_s, pi_p))
    train_jit_br = jax.jit(make_train(config, br_pi_p, pi_p))
    out_actual = jax.vmap(train_jit_actual)(rngs)
    out_br = jax.vmap(train_jit_br)(rngs)
    agent0_actual = out_actual["metrics"]["agent0"]["episode_returns"][:,:,-2,:]
    agent1_actual = out_actual["metrics"]["agent1"]["episode_returns"][:,:,-2,:]
    agent1_actual = agent1_actual.reshape((agent1_actual.shape[0], agent1_actual.shape[1], config["NUM_ENVS"], -1))
    agent1_actual = jnp.sum(agent1_actual, axis=3)
    agent0_br = out_br["metrics"]["agent0"]["episode_returns"][:,:,-2,:]
    agent1_br = out_br["metrics"]["agent1"]["episode_returns"][:,:,-2,:]
    agent1_br = agent1_br.reshape((agent1_br.shape[0], agent1_br.shape[1], config["NUM_ENVS"], -1))
    agent1_br = jnp.sum(agent1_br, axis=3)
    w_actual = agent0_actual.mean()+agent1_actual.mean()
    w_br = agent0_br.mean() + agent1_br.mean()
    c_s_p = w_actual - w_br
    print("Actual Outcome", w_actual)
    print("Selfish Outcome", w_br)
    print("C(pi_s, pi_p)",c_s_p)
    
    df_eval = pd.DataFrame({'context': ['pi_p']*160,
                'eval': ['pi_s']*160,
            'return': jnp.ravel(agent0_actual+agent1_actual).tolist()})
    
    df_br = pd.DataFrame({'context': ['pi_p']*160,
            'eval': ['best_response'] * 160,
            'return':jnp.ravel(agent0_br+agent1_br).tolist()})
    
    df3 = pd.concat([df_eval, df_br]).reset_index(drop=True)
    
    # C(pi_p, pi_p)
    rng = jax.random.PRNGKey(config["SEED"])
    rngs = jax.random.split(rng, config["NUM_SEEDS"])
    train_jit_actual = jax.jit(make_train(config, pi_p, pi_p))
    train_jit_br = jax.jit(make_train(config, br_pi_p, pi_p))
    out_actual = jax.vmap(train_jit_actual)(rngs)
    out_br = jax.vmap(train_jit_br)(rngs)
    agent0_actual = out_actual["metrics"]["agent0"]["episode_returns"][:,:,-2,:]
    agent1_actual = out_actual["metrics"]["agent1"]["episode_returns"][:,:,-2,:]
    agent1_actual = agent1_actual.reshape((agent1_actual.shape[0], agent1_actual.shape[1], config["NUM_ENVS"], -1))
    agent1_actual = jnp.sum(agent1_actual, axis=3)
    agent0_br = out_br["metrics"]["agent0"]["episode_returns"][:,:,-2,:]
    agent1_br = out_br["metrics"]["agent1"]["episode_returns"][:,:,-2,:]
    agent1_br = agent1_br.reshape((agent1_br.shape[0], agent1_br.shape[1], config["NUM_ENVS"], -1))
    agent1_br = jnp.sum(agent1_br, axis=3)
    w_actual = agent0_actual.mean()+agent1_actual.mean()
    w_br = agent0_br.mean() + agent1_br.mean()
    c_p_p = w_actual - w_br
    print("Actual Outcome", w_actual)
    print("Selfish Outcome", w_br)
    print("C(pi_p, pi_p)", c_p_p)
    
    df_eval = pd.DataFrame({'context': ['pi_p']*160,
                'eval': ['pi_p']*160,
            'return': jnp.ravel(agent0_actual+agent1_actual).tolist()})
    
    df4 = pd.concat([df_eval]).reset_index(drop=True)
    
    df = pd.concat([df1, df2, df3, df4]).reset_index(drop=True)
    print('length of df', len(df))
    df.to_csv('results/5pred-1prey.csv')
    
    scores = np.array([[c_s_s, c_p_s], [c_s_p, c_p_p]]).T

    plt.figure(figsize=(10,8))
    sns.set(font_scale=1.5)
    # df_heatmap = cscores[cscores['welfare']=='Bentham']

    # df_pivot = df_heatmap.pivot(index='evaluated_policy', columns='context_policy', values='score')
    df = pd.DataFrame(data = scores,  
                  index = ["$\pi_{\mathrm{Selfish}}$", "$\pi_{\mathrm{Prosocial}}$"],  
                  columns = ["$\pi_{\mathrm{Selfish}}$", "$\pi_{\mathrm{Prosocial}}$"]) 
    sns.heatmap(data=df, annot=True, fmt='.1f', linewidths=0.5, cmap='RdYlGn', center=0)
    plt.ylabel('Evaluated Policy')
    plt.xlabel('Context Policy')
    plt.savefig('facmac-5pred-5prey-total_return.pdf', format='pdf', bbox_inches='tight')
    plt.clf()
    
    # print("returned episode returns", out_actual["metrics"]["agent0"]["returned_discounted_episode_returns"].shape)
    # print("trajectory return", out_actual["metrics"]["agent0"]["returned_episode_returns"][0,:,:,0])
    # print("trajectory lengths", out_actual["metrics"]["agent0"]["returned_episode_lengths"][0,:,:,0])
    # print()
    # print("returned episode returns", out_br["metrics"]["agent0"]["returned_episode_returns"].shape)
    # print("trajectory return", out_br["metrics"]["agent0"]["returned_episode_returns"][0,:,:,0])
    # print("trajectory lengths", out_br["metrics"]["agent0"]["returned_episode_lengths"][0,:,:,0])
    

    
    # print("Actual Welfare (Discounted)", out_actual["metrics"]["agent0"]["returned_discounted_episode_returns"][:,:,-1,:].mean())
    # print("BR Welfare (Discounted)", out_br["metrics"]["agent0"]["returned_discounted_episode_returns"][:,:,-1,:].mean())
    return
    # print(out)
    # save params
    # env_name = config["ENV_NAME"]
    # alg_name = "IPPO"
    # if config['SAVE_PATH'] is not None:

    #     def save_params(params: Dict, filename: Union[str, os.PathLike]) -> None:
    #         flattened_dict = flatten_dict(params, sep=',')
    #         save_file(flattened_dict, filename)

    #     model_state = out['runner_state'][0]
    #     params = jax.tree_map(lambda x: x[0], model_state.params) # save only params of the first run
    #     save_dir = os.path.join(config['SAVE_PATH'], env_name, "adversary0")
    #     os.makedirs(save_dir, exist_ok=True)
    #     save_params(params, f'{save_dir}/{alg_name}.safetensors')
        
    #     model_state = out['runner_state'][1]
    #     params = jax.tree_map(lambda x: x[0], model_state.params) # save only params of the first run
    #     save_dir = os.path.join(config['SAVE_PATH'], env_name, "adversary1")
    #     os.makedirs(save_dir, exist_ok=True)
    #     save_params(params, f'{save_dir}/{alg_name}.safetensors')
    #     print(f'Parameters of first batch saved in {save_dir}/{alg_name}.safetensors')
        
        # train_state = out['runner_state'][0]
        # save_args = orbax_utils.save_args_from_target(train_state)
        # orbax_checkpointer = orbax.checkpoint.PyTreeCheckpointer()
        # save_loc = 'tmp/orbax/checkpoint_rnn'
        # orbax_checkpointer.save(save_loc, train_state, save_args=save_args)

    # logging
    updates_x0 = jnp.arange(out["metrics"]["agent0"]["total_loss"][0].shape[0])
    updates_x1 = jnp.arange(out["metrics"]["agent1"]["total_loss"][0].shape[0])
    loss_table0 = jnp.stack([updates_x0, out["metrics"]["agent0"]["total_loss"].mean(axis=0), out["metrics"]["agent0"]["actor_loss"].mean(axis=0), out["metrics"]["agent0"]["critic_loss"].mean(axis=0), out["metrics"]["agent0"]["entropy"].mean(axis=0), out["metrics"]["agent0"]["ratio"].mean(axis=0)], axis=1)
    loss_table1 = jnp.stack([updates_x1, out["metrics"]["agent1"]["total_loss"].mean(axis=0), out["metrics"]["agent1"]["actor_loss"].mean(axis=0), out["metrics"]["agent1"]["critic_loss"].mean(axis=0), out["metrics"]["agent1"]["entropy"].mean(axis=0), out["metrics"]["agent1"]["ratio"].mean(axis=0)], axis=1)        
    loss_table0 = wandb.Table(data=loss_table0.tolist(), columns=["updates", "total_loss", "actor_loss", "critic_loss", "entropy", "ratio"])
    loss_table1 = wandb.Table(data=loss_table1.tolist(), columns=["updates", "total_loss", "actor_loss", "critic_loss", "entropy", "ratio"])
    updates_x0 = jnp.arange(out["metrics"]["agent0"]["returned_episode_returns"][0].shape[0])
    updates_x1 = jnp.arange(out["metrics"]["agent1"]["returned_episode_returns"][0].shape[0])
    returns_table0 = jnp.stack([updates_x0, out["metrics"]["agent0"]["returned_episode_returns"].mean(axis=0)], axis=1)
    returns_table1 = jnp.stack([updates_x1, out["metrics"]["agent1"]["returned_episode_returns"].mean(axis=0)], axis=1)
    returns_table0 = wandb.Table(data=returns_table0.tolist(), columns=["updates0", "returns0"])
    returns_table1 = wandb.Table(data=returns_table1.tolist(), columns=["updates1", "returns1"])
    wandb.log({
        "returns_plot0": wandb.plot.line(returns_table0, "updates0", "returns0", title="returns_vs_updates0"),
        # "returns0": out["metrics"]["returned_episode_returns"][:,-1].mean(),
        # "total_loss_plot0": wandb.plot.line(loss_table0, "updates", "total_loss", title="total_loss_vs_updates0"),
        # "actor_loss_plot0": wandb.plot.line(loss_table0, "updates", "actor_loss", title="actor_loss_vs_updates0"),
        # "critic_loss_plot0": wandb.plot.line(loss_table0, "updates", "critic_loss", title="critic_loss_vs_updates0"),
        # "entropy_plot0": wandb.plot.line(loss_table0, "updates", "entropy", title="entropy_vs_updates0"),
        # "ratio_plot0": wandb.plot.line(loss_table0, "updates", "ratio", title="ratio_vs_updates0"),
        "returns_plot1": wandb.plot.line(returns_table1, "updates1", "returns1", title="returns_vs_updates1"),
        # "returns1": out["metrics"]["returned_episode_returns"][:,-1].mean(),
        # "total_loss_plot1": wandb.plot.line(loss_table1, "updates", "total_loss", title="total_loss_vs_updates1"),
        # "actor_loss_plot1": wandb.plot.line(loss_table1, "updates", "actor_loss", title="actor_loss_vs_updates1"),
        # "critic_loss_plot1": wandb.plot.line(loss_table1, "updates", "critic_loss", title="critic_loss_vs_updates1"),
        # "entropy_plot1": wandb.plot.line(loss_table1, "updates", "entropy", title="entropy_vs_updates1"),
        # "ratio_plot1": wandb.plot.line(loss_table1, "updates", "ratio", title="ratio_vs_updates1"),
    })
    
    # import pdb;

    # pdb.set_trace()


if __name__ == "__main__":
    main()