"""Splatfacto 兼容入口；修正日程和 gsplat 1.5.3 的透明度重置错误。"""

import functools
import inspect
import sys


def patch_opacity_reset(strategy_class, reset_function):
    """只修补已知错误版本，未来正确的依赖直接沿用原行为。"""
    original = strategy_class.step_post_backward
    if getattr(original, '_sharp_reset_fixed', False):
        return False
    if '== 0 & step > 0' not in inspect.getsource(original):
        return False

    @functools.wraps(original)
    def corrected(self, params, optimizers, state, step, info, packed=False):
        original(self, params, optimizers, state, step, info, packed=packed)
        if 0 < step < self.refine_stop_iter and step % self.reset_every == 0:
            reset_function(params=params, optimizers=optimizers, state=state, value=self.prune_opa * 2.0)

    corrected._sharp_reset_fixed = True
    strategy_class.step_post_backward = corrected
    return True


def configure_schedule(config, total_steps):
    """优化器和高斯细化日程随总步数一起调整。"""
    config.pipeline.model.stop_split_at = max(501, round(total_steps * 0.8))
    config.pipeline.model.num_downscales = 1 if total_steps <= 8000 else 0
    for optimizer in config.optimizers.values():
        scheduler = optimizer.get('scheduler')
        if scheduler is not None and hasattr(scheduler, 'max_steps'):
            scheduler.max_steps = total_steps


def main():
    from gsplat.strategy import DefaultStrategy
    from gsplat.strategy.ops import reset_opa
    from nerfstudio.configs.method_configs import method_configs
    from nerfstudio.scripts.train import entrypoint

    args = sys.argv[1:]
    if '--max-num-iterations' in args:
        index = args.index('--max-num-iterations')
        configure_schedule(method_configs['splatfacto'], int(args[index + 1]))
    if patch_opacity_reset(DefaultStrategy, reset_opa):
        print('Applied gsplat 1.5.3 opacity reset compatibility fix.', flush=True)
    entrypoint()


if __name__ == '__main__':
    main()
