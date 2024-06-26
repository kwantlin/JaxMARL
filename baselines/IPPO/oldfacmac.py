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
            64, kernel_init=orthogonal(np.sqrt(2)), bias_init=constant(0.0)
        )(x)
        actor_mean = activation(actor_mean)
        actor_mean = nn.Dense(
            64, kernel_init=orthogonal(np.sqrt(2)), bias_init=constant(0.0)
        )(actor_mean)
        actor_mean = activation(actor_mean)
        actor_mean = nn.Dense(
            self.action_dim, kernel_init=orthogonal(0.01), bias_init=constant(0.0)
        )(actor_mean)
        actor_logtstd = self.param('log_std', nn.initializers.zeros, (self.action_dim,))
        pi = distrax.MultivariateNormalDiag(actor_mean, jnp.exp(actor_logtstd))

        critic = nn.Dense(
            64, kernel_init=orthogonal(np.sqrt(2)), bias_init=constant(0.0)
        )(x)
        critic = activation(critic)
        critic = nn.Dense(
            64, kernel_init=orthogonal(np.sqrt(2)), bias_init=constant(0.0)
        )(critic)
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


def batchify(x: dict, agent_list, num_actors):
    max_dim = max([x[a].shape[-1] for a in agent_list])
    def pad(z, length):
        return jnp.concatenate([z, jnp.zeros(z.shape[:-1] + [length - z.shape[-1]])], -1)

    x = jnp.stack([x[a] if x[a].shape[-1] == max_dim else pad(x[a]) for a in agent_list])
    return x


def unbatchify(x: jnp.ndarray, agent_list, num_envs, num_actors):
    x = x.reshape((num_actors, num_envs, -1))
    return {a: x[i] for i, a in enumerate(agent_list)}


def make_train(config):
    env = jaxmarl.make(config["ENV_NAME"], **config["ENV_KWARGS"])
    config["NUM_ACTORS"] = config["NUM_ENVS"]
    config["NUM_UPDATES"] = (
            config["TOTAL_TIMESTEPS"] // config["NUM_STEPS"] // config["NUM_ENVS"]
    )
    config["MINIBATCH_SIZE"] = (
            config["NUM_ACTORS"] * config["NUM_STEPS"] // config["NUM_MINIBATCHES"]
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
        network = [ActorCritic(env.action_space(env.agents[0]).shape[0], activation=config["ACTIVATION"]) for i in range(env.num_adversaries)]
        rng, _rng = jax.random.split(rng)
        # print(env.observation_space(env.agents[0]).shape)
        init_x = jnp.zeros(env.observation_space(env.agents[0]).shape)
        network_params = [net.init(_rng, init_x) for net in network]
        if config["ANNEAL_LR"]:
            tx = optax.chain(
                optax.clip_by_global_norm(config["MAX_GRAD_NORM"]),
                optax.adam(learning_rate=linear_schedule, eps=1e-5),
            )
        else:
            tx = optax.chain(optax.clip_by_global_norm(config["MAX_GRAD_NORM"]), optax.adam(config["LR"], eps=1e-5))

        train_state = [TrainState.create(
            apply_fn=network[i].apply,
            params=network_params[i],
            tx=tx,
        ) for i in range(env.num_adversaries)]

        # INIT ENV
        rng, _rng = jax.random.split(rng)
        reset_rng = jax.random.split(_rng, config["NUM_ENVS"])
        obsv, env_state = jax.vmap(env.reset)(reset_rng)

        # TRAIN LOOP
        def _update_step(runner_state, unused):
            # COLLECT TRAJECTORIES
            def _env_step(runner_state, unused):
                train_state, env_state, last_obs, rng = runner_state

                obs_batch = batchify(last_obs, env.agents, config["NUM_ACTORS"])
                print("obs_batch", obs_batch.shape)
                # SELECT ACTION
                rng, _rng = jax.random.split(rng)

                pi_values = [network[i].apply(train_state[i].params, obs_batch[i]) for i in range(env.num_adversaries)]
                pi = [i[0] for i in pi_values]
                value = [i[1] for i in pi_values]
                # print("pi", pi)
                actions = [pi[i].sample(seed=_rng) for i in range(env.num_adversaries)]
                log_prob = [pi[i].log_prob(actions[i]) for i in range(env.num_adversaries)]
                for _ in range(env.num_good_agents):
                    actions.append(jnp.zeros(actions[0].shape))
                    value.append(0)
                    log_prob.append(0)
                print("actions", actions)
                action = jnp.stack([a for a in actions])
                print("action", action)
                env_act = unbatchify(action, env.agents, config["NUM_ENVS"], env.num_agents)
                print("env_act", env_act)
                # STEP ENV
                rng, _rng = jax.random.split(rng)
                rng_step = jax.random.split(_rng, config["NUM_ENVS"])
                obsv, env_state, reward, done, info = jax.vmap(env.step)(
                    rng_step, env_state, env_act,
                )
                print("info before", info)
                # info = jax.tree_map(lambda x: x.reshape((config["NUM_ACTORS"])), info)
                # print("info", info)
                print("info after", jax.tree_map(lambda x: x[:,0], info))
                transition = [Transition(
                    batchify(done, env.agents, config["NUM_ACTORS"]).squeeze()[i],
                    action[i],
                    value[i],
                    batchify(reward, env.agents, config["NUM_ACTORS"]).squeeze()[i],
                    log_prob[i],
                    obs_batch[i],
                    jax.tree_map(lambda x: x[:,i], info),
                ) for i in range(env.num_agents)]
                runner_state = (train_state, env_state, obsv, rng)
                return runner_state, transition

            runner_state, traj_batch = jax.lax.scan(
                _env_step, runner_state, None, config["NUM_STEPS"]
            )
            
            # CALCULATE ADVANTAGE
            train_state, env_state, last_obs, rng = runner_state
            
            last_obs_batch = batchify(last_obs, env.agents, config["NUM_ACTORS"])
            # train_state_update = train_state[i] if type(train_state)==list else train_state #TODO
            print("STATUS at start of for loop", type(train_state))
            assert (
                        type(train_state) == list
                ), "train_state should be list"
            last_val = [network[i].apply(train_state[i], last_obs_batch[i]) for i in range(env.num_adversaries)]

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

            advantages, targets = _calculate_gae(traj_batch, last_val)

            # UPDATE NETWORK
            def _update_epoch(update_state, unused):
                def _update_minbatch(train_state, batch_info):
                    traj_batch, advantages, targets = batch_info

                    def _loss_fn(params, traj_batch, gae, targets):
                        # RERUN NETWORK
                        pi, value = network[i].apply(params, traj_batch.obs)
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

                    grad_fn = jax.value_and_grad(_loss_fn, has_aux=True)
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

                train_state, traj_batch, advantages, targets, rng = update_state
                rng, _rng = jax.random.split(rng)
                batch_size = config["MINIBATCH_SIZE"] * config["NUM_MINIBATCHES"]
                print("batch_size", batch_size)
                assert (
                        batch_size == config["NUM_STEPS"] * config["NUM_ACTORS"]
                ), "batch size must be equal to number of steps * number of actors"
                permutation = jax.random.permutation(_rng, batch_size)
                batch = (traj_batch, advantages, targets)
                print("shape", advantages.shape, targets.shape)
                batch = jax.tree_util.tree_map(
                    lambda x: x.reshape((batch_size,) + x.shape[2:]), batch
                )
                shuffled_batch = jax.tree_util.tree_map(
                    lambda x: jnp.take(x, permutation, axis=0), batch
                )
                minibatches = jax.tree_util.tree_map(
                    lambda x: jnp.reshape(
                        x, [config["NUM_MINIBATCHES"], -1] + list(x.shape[1:])
                    ),
                    shuffled_batch,
                )
                train_state, loss_info = jax.lax.scan(
                    _update_minbatch, train_state, minibatches
                )
                update_state = (train_state, traj_batch, advantages, targets, rng)
                return update_state, loss_info
        
            def callback(metric):
                wandb.log(
                    metric
                )

            # train_state_update = train_state[i] if type(train_state)==list else train_state
            update_state = (train_state[i], traj_batch, advantages, targets, rng) #TODO 
            update_state, loss_info = jax.lax.scan(
                _update_epoch, update_state, None, config["UPDATE_EPOCHS"]
            )
            
            train_state = update_state[0]
            metric = traj_batch.info
            rng = update_state[-1]

            r0 = {"ratio0": loss_info["ratio"][0,0].mean()}
            # jax.debug.print('ratio0 {x}', x=r0["ratio0"])
            loss_info = jax.tree_map(lambda x: x.mean(), loss_info)
            metric = jax.tree_map(lambda x: x.mean(), metric)
            metric = {**metric, **loss_info, **r0}
            jax.experimental.io_callback(callback, None, metric)
            runner_state = (train_state, env_state, last_obs, rng)
            print("STATUS", type(train_state), len(last_obs))
            runner_states.append(runner_state)
            metrics.append(metric)
 
            runner_state = ([state[0] for state in runner_states], runner_states[0][1], runner_states[0][2], runner_states[0][3])
            return runner_state, metrics

        rng, _rng = jax.random.split(rng)
        runner_state = (train_state, env_state, obsv, _rng)
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
    print(out)
    # save params
    env_name = config["ENV_NAME"]
    alg_name = "IPPO"
    if config['SAVE_PATH'] is not None:

        def save_params(params: Dict, filename: Union[str, os.PathLike]) -> None:
            flattened_dict = flatten_dict(params, sep=',')
            save_file(flattened_dict, filename)

        model_state = out['runner_state'][0]
        params = jax.tree_map(lambda x: x[0], model_state.params) # save only params of the firt run
        save_dir = os.path.join(config['SAVE_PATH'], env_name)
        os.makedirs(save_dir, exist_ok=True)
        save_params(params, f'{save_dir}/{alg_name}.safetensors')
        print(f'Parameters of first batch saved in {save_dir}/{alg_name}.safetensors')

    # logging
    updates_x = jnp.arange(out["metrics"]["total_loss"][0].shape[0])
    loss_table = jnp.stack([updates_x, out["metrics"]["total_loss"].mean(axis=0), out["metrics"]["actor_loss"].mean(axis=0), out["metrics"]["critic_loss"].mean(axis=0), out["metrics"]["entropy"].mean(axis=0), out["metrics"]["ratio"].mean(axis=0)], axis=1)    
    loss_table = wandb.Table(data=loss_table.tolist(), columns=["updates", "total_loss", "actor_loss", "critic_loss", "entropy", "ratio"])
    updates_x = jnp.arange(out["metrics"]["returned_episode_returns"][0].shape[0])
    returns_table = jnp.stack([updates_x, out["metrics"]["returned_episode_returns"].mean(axis=0)], axis=1)
    returns_table = wandb.Table(data=returns_table.tolist(), columns=["updates", "returns"])
    wandb.log({
        "returns_plot": wandb.plot.line(returns_table, "updates", "returns", title="returns_vs_updates"),
        # "returns": out["metrics"]["returned_episode_returns"][:,-1].mean(),
        "total_loss_plot": wandb.plot.line(loss_table, "updates", "total_loss", title="total_loss_vs_updates"),
        "actor_loss_plot": wandb.plot.line(loss_table, "updates", "actor_loss", title="actor_loss_vs_updates"),
        "critic_loss_plot": wandb.plot.line(loss_table, "updates", "critic_loss", title="critic_loss_vs_updates"),
        "entropy_plot": wandb.plot.line(loss_table, "updates", "entropy", title="entropy_vs_updates"),
        "ratio_plot": wandb.plot.line(loss_table, "updates", "ratio", title="ratio_vs_updates"),
    })
    
    # import pdb;

    # pdb.set_trace()


if __name__ == "__main__":
    main()