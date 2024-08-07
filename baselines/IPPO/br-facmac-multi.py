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
    print("unbatchify", x.shape)
    return {a: x[i] for i, a in enumerate(agent_list)}

def flatten_agents(x):
    # print("FLATTEN SHAPE", x.shape)
    return x.reshape((x.shape[0]*x.shape[1], ))

def make_train(config):
    env = MultiFacmacMPE(**config["ENV_KWARGS"])
    print("made env")
    config["NUM_ACTORS"] = env.num_agents * config["NUM_ENVS"]
    config["NUM_UPDATES"] = (
            config["TOTAL_TIMESTEPS"] // config["NUM_STEPS"] // config["NUM_ENVS"]
    )
    config["MINIBATCH_SIZE"] = (
            config["NUM_ACTORS"] * config["NUM_STEPS"] // config["NUM_MINIBATCHES"]
    )
    print("minibatch size", config["MINIBATCH_SIZE"])

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
        print("randoms", _rng0, _rng1)
        print(env.observation_space(env.agents[0]).shape)
        print(env.agents)
        init_x = jnp.zeros(env.observation_space(env.agents[0]).shape)
        print("init x", init_x)
        network_params0 = network0.init(_rng0, init_x)
        
        def load_params(filename):
            flattened_dict = load_file(filename)
            return unflatten_dict(flattened_dict, sep=',')

        network_params1 = load_params("ckpt/MPE_simple_facmac_v1/selfish/IPPO.safetensors")
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
                print("obs_batch", obs_batch.shape)
                print("obs_batch values", obs_batch)

                # SELECT ACTION
                rng, _rng0, _rng1 = jax.random.split(rng, num=3)

                pi0, value0 = network0.apply(train_state0.params, obs_batch[0:1].reshape((obs_batch[0:1].shape[0]*obs_batch[0:1].shape[1], -1)))
                pi1, value1 = network1.apply(train_state1.params, obs_batch[1:env.num_adversaries].reshape((obs_batch[1:env.num_adversaries].shape[0]*obs_batch[1:env.num_adversaries].shape[1], -1)))
                print("value", value0, value1)
                action0 = pi0.sample(seed=_rng0)
                action1 = pi1.sample(seed=_rng1)
                print("action", action0, action1)
                action = jnp.concatenate([action0, action1], axis=0)
                for _ in range(env.num_good_agents):
                    action = jnp.concatenate([action, jnp.zeros(action0.shape)], axis=0)
                print("action", action.shape)
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
                # info = jax.tree_map(lambda x: x.reshape((config["NUM_ACTORS"])), info)
                # print("info", info)
                print("obs_batch before transition", obs_batch.shape)
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

            # CALCULATE ADVANTAGE
            train_state0, train_state1, env_state, last_obs, rng = runner_state
            last_obs_batch = batchify(last_obs, env.agents, config["NUM_ACTORS"])
            _, last_val0 = network0.apply(train_state0.params, last_obs_batch[0:1].reshape((last_obs_batch[0:1].shape[0]*last_obs_batch[0:1].shape[1], -1)))
            _, last_val1 = network1.apply(train_state1.params, last_obs_batch[1:env.num_adversaries].reshape((last_obs_batch[1:env.num_adversaries].shape[0]*last_obs_batch[1:env.num_adversaries].shape[1], -1)))

            def _calculate_gae(traj_batch, last_val):
                def _get_advantages(gae_and_next_value, transition):
                    gae, next_value = gae_and_next_value
                    done, value, reward = (
                        transition.done,
                        transition.value,
                        transition.reward,
                    )
                    delta = reward + config["GAMMA"] * next_value * (1 - done) - value
                    gae = (
                            delta
                            + config["GAMMA"] * config["GAE_LAMBDA"] * (1 - done) * gae
                    )
                    return (gae, value), gae

                _, advantages = jax.lax.scan(
                    _get_advantages,
                    (jnp.zeros_like(last_val), last_val),
                    traj_batch,
                    reverse=True,
                    unroll=8,
                )
                return advantages, advantages + traj_batch.value

            # print("traj batch last val", type(traj_batch0), last_val0.shape)
            advantages0, targets0 = _calculate_gae(traj_batch0, last_val0)
            # print("advantages", advantages0.shape)
            advantages1, targets1 = _calculate_gae(traj_batch1, last_val1)

            # UPDATE NETWORK
            def _update_epoch(update_state, unused):
                def _update_minbatch0(train_state, batch_info):
                    traj_batch, advantages, targets = batch_info

                    def _loss_fn0(params, traj_batch, gae, targets):
                        # RERUN NETWORK
                        pi, value = network0.apply(params, traj_batch.obs)
                        log_prob = pi.log_prob(traj_batch.action)

                        # CALCULATE VALUE LOSS
                        value_pred_clipped = traj_batch.value + (
                                value - traj_batch.value
                        ).clip(-config["CLIP_EPS"], config["CLIP_EPS"])
                        value_losses = jnp.square(value - targets)
                        value_losses_clipped = jnp.square(value_pred_clipped - targets)
                        value_loss = (
                                0.5 * jnp.maximum(value_losses, value_losses_clipped).mean()
                        )

                        # CALCULATE ACTOR LOSS
                        ratio = jnp.exp(log_prob - traj_batch.log_prob)
                        gae = (gae - gae.mean()) / (gae.std() + 1e-8)
                        loss_actor1 = ratio * gae
                        loss_actor2 = (
                                jnp.clip(
                                    ratio,
                                    1.0 - config["CLIP_EPS"],
                                    1.0 + config["CLIP_EPS"],
                                )
                                * gae
                        )
                        loss_actor = -jnp.minimum(loss_actor1, loss_actor2)
                        loss_actor = loss_actor.mean()
                        entropy = pi.entropy().mean()

                        total_loss = (
                                loss_actor
                                + config["VF_COEF"] * value_loss
                                - config["ENT_COEF"] * entropy
                        )
                        return total_loss, (value_loss, loss_actor, entropy, ratio)

                    grad_fn = jax.value_and_grad(_loss_fn0, has_aux=True)
                    total_loss, grads = grad_fn(
                        train_state.params, traj_batch, advantages, targets
                    )
                    train_state = train_state.apply_gradients(grads=grads)
                    
                    loss_info = {
                        "total_loss": total_loss[0],
                        "actor_loss": total_loss[1][1],
                        "critic_loss": total_loss[1][0],
                        "entropy": total_loss[1][2],
                        "ratio": total_loss[1][3],
                    }
                    
                    return train_state,  loss_info
                
                def _update_minbatch1(train_state, batch_info):
                    traj_batch, advantages, targets = batch_info

                    def _loss_fn1(params, traj_batch, gae, targets):
                        # RERUN NETWORK
                        pi, value = network1.apply(params, traj_batch.obs)
                        log_prob = pi.log_prob(traj_batch.action)

                        # CALCULATE VALUE LOSS
                        value_pred_clipped = traj_batch.value + (
                                value - traj_batch.value
                        ).clip(-config["CLIP_EPS"], config["CLIP_EPS"])
                        value_losses = jnp.square(value - targets)
                        value_losses_clipped = jnp.square(value_pred_clipped - targets)
                        value_loss = (
                                0.5 * jnp.maximum(value_losses, value_losses_clipped).mean()
                        )

                        # CALCULATE ACTOR LOSS
                        ratio = jnp.exp(log_prob - traj_batch.log_prob)
                        gae = (gae - gae.mean()) / (gae.std() + 1e-8)
                        loss_actor1 = ratio * gae
                        loss_actor2 = (
                                jnp.clip(
                                    ratio,
                                    1.0 - config["CLIP_EPS"],
                                    1.0 + config["CLIP_EPS"],
                                )
                                * gae
                        )
                        loss_actor = -jnp.minimum(loss_actor1, loss_actor2)
                        loss_actor = loss_actor.mean()
                        entropy = pi.entropy().mean()

                        total_loss = (
                                loss_actor
                                + config["VF_COEF"] * value_loss
                                - config["ENT_COEF"] * entropy
                        )
                        return total_loss, (value_loss, loss_actor, entropy, ratio)

                    # grad_fn = jax.value_and_grad(_loss_fn1, has_aux=True)
                    total_loss = _loss_fn1(
                        train_state.params, traj_batch, advantages, targets
                    )
                    # train_state = train_state.apply_gradients(grads=grads)
                    print("total_loss", total_loss)
                    loss_info = {
                        "total_loss": total_loss[0],
                        "actor_loss": total_loss[1][1],
                        "critic_loss": total_loss[1][0],
                        "entropy": total_loss[1][2],
                        "ratio": total_loss[1][3],
                    }
                    
                    return train_state,  loss_info

                train_state0, train_state1, traj_batch0, traj_batch1, advantages0, advantages1, targets0, targets1, rng = update_state
                rng, _rng0, _rng1 = jax.random.split(rng, 3)
                batch_size0 = config["MINIBATCH_SIZE"] * config["NUM_MINIBATCHES"] // env.num_agents # TODO
                batch_size1 = config["MINIBATCH_SIZE"] * config["NUM_MINIBATCHES"] // env.num_agents * (env.num_adversaries - 1) # TODO
                print("batch_size", batch_size0)
                print("config[MINIBATCH_SIZE]", config["MINIBATCH_SIZE"])
                print("config[NUM_MINIBATCHES]", config["NUM_MINIBATCHES"])
                print("config[NUM_STEPS] // config[NUM_MINIBATCHES])",  config["NUM_STEPS"] // config["NUM_MINIBATCHES"])
                # assert (
                #         batch_size == config["NUM_STEPS"] * config["NUM_ACTORS"] // 3 # TODO
                # ), "batch size must be equal to number of steps * number of actors"
                permutation0 = jax.random.permutation(_rng0, batch_size0)
                permutation1 = jax.random.permutation(_rng1, batch_size1)
                print("advantages", advantages1.shape, targets1.shape)
                batch0 = (traj_batch0, advantages0, targets0)
                batch1 = (traj_batch1, advantages1, targets1)
                print("batch1", traj_batch1)
                batch0 = jax.tree_util.tree_map(
                    lambda x: x.reshape((batch_size0,) + x.shape[2:]), batch0
                )
                batch1 = jax.tree_util.tree_map(
                    lambda x: x.reshape((batch_size1,) + x.shape[2:]), batch1
                )
                shuffled_batch0 = jax.tree_util.tree_map(
                    lambda x: jnp.take(x, permutation0, axis=0), batch0
                )
                shuffled_batch1 = jax.tree_util.tree_map(
                    lambda x: jnp.take(x, permutation1, axis=0), batch1
                )
                minibatches0 = jax.tree_util.tree_map(
                    lambda x: jnp.reshape(
                        x, [config["NUM_MINIBATCHES"], -1] + list(x.shape[1:])
                    ),
                    shuffled_batch0,
                )
                minibatches1 = jax.tree_util.tree_map(
                    lambda x: jnp.reshape(
                        x, [config["NUM_MINIBATCHES"], -1] + list(x.shape[1:])
                    ),
                    shuffled_batch1,
                )
                train_state0, loss_info0 = jax.lax.scan(
                    _update_minbatch0, train_state0, minibatches0
                )
                train_state1, loss_info1 = jax.lax.scan(
                    _update_minbatch1, train_state1, minibatches1
                )
                update_state = (train_state0, train_state1, traj_batch0, traj_batch1, advantages0, advantages1, targets0, targets1, rng)
                return update_state, (loss_info0, loss_info1)
            
            def callback(metric):
                wandb.log(
                    metric
                )

            update_state = (train_state0, train_state1, traj_batch0, traj_batch1, advantages0, advantages1, targets0, targets1, rng)
            update_state, (loss_info0, loss_info1) = jax.lax.scan(
                _update_epoch, update_state, None, config["UPDATE_EPOCHS"]
            )
            train_state0 = update_state[0]
            train_state1 = update_state[1]
            metric0 = traj_batch0.info
            metric1 = traj_batch1.info
            rng = update_state[-1]

            r0 = {"ratio0": loss_info0["ratio"][0,0].mean()}
            # jax.debug.print('ratio0 {x}', x=r0["ratio0"])
            loss_info0 = jax.tree_map(lambda x: x.mean(), loss_info0)
            loss_info1 = jax.tree_map(lambda x: x.mean(), loss_info1)
            metric0 = jax.tree_map(lambda x: x[-2,:].reshape((config["NUM_ENVS"],1)), metric0)
            metric1 = jax.tree_map(lambda x: x[-2,:].reshape((config["NUM_ENVS"], env.num_adversaries-1)), metric1)
            metric = {"agent0":{**metric0, **loss_info0,}, "agent1":{**metric1, **loss_info1,}, **r0}
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
    
    rng = jax.random.PRNGKey(config["SEED"])
    rngs = jax.random.split(rng, config["NUM_SEEDS"])    
    train_jit = jax.jit(make_train(config))
    out = jax.vmap(train_jit)(rngs)
    # print(out)
    # save params
    env_name = config["ENV_NAME"]
    alg_name = "IPPO"
    if config['SAVE_PATH'] is not None:

        def save_params(params: Dict, filename: Union[str, os.PathLike]) -> None:
            flattened_dict = flatten_dict(params, sep=',')
            save_file(flattened_dict, filename)

        model_state = out['runner_state'][0]
        params = jax.tree_map(lambda x: x[0], model_state.params) # save only params of the first run
        save_dir = os.path.join(config['SAVE_PATH'], env_name, "br-selfish")
        os.makedirs(save_dir, exist_ok=True)
        save_params(params, f'{save_dir}/{alg_name}.safetensors')
        
        # model_state = out['runner_state'][1]
        # params = jax.tree_map(lambda x: x[0], model_state.params) # save only params of the first run
        # save_dir = os.path.join(config['SAVE_PATH'], env_name, "adversary1")
        # os.makedirs(save_dir, exist_ok=True)
        # save_params(params, f'{save_dir}/{alg_name}.safetensors')
        print(f'Parameters of first batch saved in {save_dir}/{alg_name}.safetensors')

    # logging
    print(out["metrics"]["agent0"]["episode_returns"].shape)
    print(out["metrics"]["agent0"]["episode_returns"].mean(axis=0).shape)
    print(out["metrics"]["agent1"]["episode_returns"].mean(axis=(0,2)))
    # updates_x0 = jnp.arange(out["metrics"]["agent0"]["total_loss"][0].shape[0])
    # updates_x1 = jnp.arange(out["metrics"]["agent1"]["total_loss"][0].shape[0])
    # loss_table0 = jnp.stack([updates_x0, out["metrics"]["agent0"]["total_loss"].mean(axis=0), out["metrics"]["agent0"]["actor_loss"].mean(axis=0), out["metrics"]["agent0"]["critic_loss"].mean(axis=0), out["metrics"]["agent0"]["entropy"].mean(axis=0), out["metrics"]["agent0"]["ratio"].mean(axis=0)], axis=1)
    # loss_table1 = jnp.stack([updates_x1, out["metrics"]["agent1"]["total_loss"].mean(axis=0), out["metrics"]["agent1"]["actor_loss"].mean(axis=0), out["metrics"]["agent1"]["critic_loss"].mean(axis=0), out["metrics"]["agent1"]["entropy"].mean(axis=0), out["metrics"]["agent1"]["ratio"].mean(axis=0)], axis=1)        
    # loss_table0 = wandb.Table(data=loss_table0.tolist(), columns=["updates", "total_loss", "actor_loss", "critic_loss", "entropy", "ratio"])
    # loss_table1 = wandb.Table(data=loss_table1.tolist(), columns=["updates", "total_loss", "actor_loss", "critic_loss", "entropy", "ratio"])
    #logging
    env = jaxmarl.make(config["ENV_NAME"], **config["ENV_KWARGS"])
    updates_x = jnp.expand_dims(jnp.arange(out["metrics"]["agent0"]["episode_returns"].shape[1]),1)
    returns_table = jnp.concatenate([updates_x, jnp.expand_dims(out["metrics"]["agent0"]["episode_returns"].mean(axis=(0,2))[:,0], 1)], axis=1)
    returns_table = wandb.Table(data=returns_table.tolist(), columns=["updates", "BR_returns"])
    wandb.log({
            # "returns_plot": wandb.plot.line_series(xs=jnp.arange(out["metrics"]["episode_returns"].shape[1]).tolist(), ys=out["metrics"]["episode_returns"].mean(axis=(0,2)).T.tolist(), keys = env.agents[:env.num_adversaries], title="Returns vs Updates", xname="Updates")
            "BR_returns_plot": wandb.plot.line(returns_table, "updates", "BR_returns", title="BR_returns"),
            # "returns": out["metrics"]["returned_episode_returns"][:,-1].mean(),
            # "total_loss_plot": wandb.plot.line(loss_table, "updates", "total_loss", title="total_loss_vs_updates"),
            # "actor_loss_plot": wandb.plot.line(loss_table, "updates", "actor_loss", title="actor_loss_vs_updates"),
            # "critic_loss_plot": wandb.plot.line(loss_table, "updates", "critic_loss", title="critic_loss_vs_updates"),
            # "entropy_plot": wandb.plot.line(loss_table, "updates", "entropy", title="entropy_vs_updates"),
        })
    # returns_table = jnp.concatenate([updates_x, out["metrics"]["episode_returns"].mean(axis=(0,2))], axis=1)
    # returns_table = wandb.Table(data=returns_table.tolist(), columns=["updates"] + env.agents[:env.num_adversaries])
    for i in range(1, env.num_adversaries):
        returns_table = jnp.concatenate([updates_x, jnp.expand_dims(out["metrics"]["agent1"]["episode_returns"].mean(axis=(0,2))[:,i], 1)], axis=1)
        returns_table = wandb.Table(data=returns_table.tolist(), columns=["updates", "returns"+str(i)])
        wandb.log({
            # "returns_plot": wandb.plot.line_series(xs=jnp.arange(out["metrics"]["episode_returns"].shape[1]).tolist(), ys=out["metrics"]["episode_returns"].mean(axis=(0,2)).T.tolist(), keys = env.agents[:env.num_adversaries], title="Returns vs Updates", xname="Updates")
            "returns"+str(i)+"_plot": wandb.plot.line(returns_table, "updates", "returns"+str(i), title="returns"+str(i)+"_vs_updates"),
            # "returns": out["metrics"]["returned_episode_returns"][:,-1].mean(),
            # "total_loss_plot": wandb.plot.line(loss_table, "updates", "total_loss", title="total_loss_vs_updates"),
            # "actor_loss_plot": wandb.plot.line(loss_table, "updates", "actor_loss", title="actor_loss_vs_updates"),
            # "critic_loss_plot": wandb.plot.line(loss_table, "updates", "critic_loss", title="critic_loss_vs_updates"),
            # "entropy_plot": wandb.plot.line(loss_table, "updates", "entropy", title="entropy_vs_updates"),
        })
    
    # updates_x0 = jnp.arange(out["metrics"]["agent0"]["episode_returns"][0].shape[0])
    # updates_x1 = jnp.arange(out["metrics"]["agent1"]["episode_returns"][0].shape[0])
    # returns_table0 = jnp.stack([updates_x0, out["metrics"]["agent0"]["episode_returns"].mean(axis=(0,2))], axis=1)
    # returns_table1 = jnp.stack([updates_x1, out["metrics"]["agent1"]["episode_returns"].mean(axis=(0,2))], axis=1)
    # returns_table0 = wandb.Table(data=returns_table0.tolist(), columns=["updates0", "returns0"])
    # returns_table1 = wandb.Table(data=returns_table1.tolist(), columns=["updates1", "returns1"])
    # wandb.log({
    #     "returns_plot0": wandb.plot.line(returns_table0, "updates0", "returns0", title="returns_vs_updates0"),
    #     # "returns0": out["metrics"]["episode_returns"][:,-1].mean(),
    #     # "total_loss_plot0": wandb.plot.line(loss_table0, "updates", "total_loss", title="total_loss_vs_updates0"),
    #     # "actor_loss_plot0": wandb.plot.line(loss_table0, "updates", "actor_loss", title="actor_loss_vs_updates0"),
    #     # "critic_loss_plot0": wandb.plot.line(loss_table0, "updates", "critic_loss", title="critic_loss_vs_updates0"),
    #     # "entropy_plot0": wandb.plot.line(loss_table0, "updates", "entropy", title="entropy_vs_updates0"),
    #     # "ratio_plot0": wandb.plot.line(loss_table0, "updates", "ratio", title="ratio_vs_updates0"),
    #     "returns_plot1": wandb.plot.line(returns_table1, "updates1", "returns1", title="returns_vs_updates1"),
    #     # "returns1": out["metrics"]["episode_returns"][:,-1].mean(),
    #     # "total_loss_plot1": wandb.plot.line(loss_table1, "updates", "total_loss", title="total_loss_vs_updates1"),
    #     # "actor_loss_plot1": wandb.plot.line(loss_table1, "updates", "actor_loss", title="actor_loss_vs_updates1"),
    #     # "critic_loss_plot1": wandb.plot.line(loss_table1, "updates", "critic_loss", title="critic_loss_vs_updates1"),
    #     # "entropy_plot1": wandb.plot.line(loss_table1, "updates", "entropy", title="entropy_vs_updates1"),
    #     # "ratio_plot1": wandb.plot.line(loss_table1, "updates", "ratio", title="ratio_vs_updates1"),
    # })
    
    # import pdb;

    # pdb.set_trace()


if __name__ == "__main__":
    main()