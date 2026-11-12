"""Measure real desktop exposure-tap reuse without changing production settings."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import os
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor'))
from desktop import imaging
from spektrafilm import Simulator
from desktop.compute import status as compute_status
from spektrafilm.model.grain import set_grain_seed_offset


def milliseconds(call):
    start = time.perf_counter()
    value = call()
    return value, round((time.perf_counter() - start) * 1000, 4)


def reset_contexts():
    with imaging._SPECTRAL_CONTEXTS_LOCK:
        imaging._SPECTRAL_CONTEXTS.clear()
        imaging._SPECTRAL_CONTEXT_SIGNATURES.clear()


def compare(a, b):
    delta = np.abs(np.asarray(a).astype(np.float64) - np.asarray(b).astype(np.float64))
    return dict(exactly_equal=bool(not np.any(delta)), max_abs=float(delta.max()),
                mean_abs=float(delta.mean()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=ROOT / 'output/mask-reference/source-windsock.jpg')
    parser.add_argument('--sizes', type=int, nargs='+', default=[64, 256, 640, 1024])
    parser.add_argument('--repetitions', type=int, default=5)
    parser.add_argument('--output', type=Path, default=ROOT / 'output/perf-preview-tap-cache.json')
    args = parser.parse_args()
    original_init = imaging.init_film_params

    def deterministic_params(stock, paper):
        params = original_init(stock, paper)
        # Grain uses the engine's fixed channel/sublayer seeds; only glare is random.
        params.print_render.glare.active = False
        return params

    def render(image, settings):
        return imaging.render(image, settings, preview=True)

    settings = imaging.Settings(spectral=True, grain=12, halation=12)
    if not args.source.is_file() or not args.sizes or min(args.sizes)<1 or args.repetitions<1:
        parser.error("Source must exist and sizes/repetitions must be positive")
    os.environ["SPEKTRAFILM_COMPUTE"]="auto"
    set_grain_seed_offset(0)
    original,decode_ms=milliseconds(lambda: imaging.read_photo(str(args.source),max_edge=max(args.sizes)))
    with args.source.open("rb") as stream:
        source_hash=hashlib.file_digest(stream,"sha256").hexdigest()
    report = dict(
        measured_at=time.strftime('%Y-%m-%d %H:%M:%S %z'),
        scope='Actual grain+DIR desktop render wall time from bounded decoded RGB8 PIL proxy through output PIL image, compute auto; excludes decode, Qt dispatch, export and disk write',
        source=dict(path=str(args.source),sha256=source_hash,decoded_proxy_dimensions=list(original.size),
                    original_dimensions=list(original.info.get('source_size',original.size)),decode_ms=decode_ms,
                    decode_policy='read_photo(max_edge=max requested size), bounded RAW half-size decode then resize; never full-resolution read_photo'),
        implementation_sha256={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [ROOT/'desktop/imaging.py', ROOT/'vendor/spektrafilm/runtime/process.py',
                         ROOT/'vendor/spektrafilm/runtime/params_builder.py',ROOT/'desktop/compute.py',ROOT/'desktop/gpu_gamut_prototype.py']},
        environment=dict(os=platform.platform(), python=sys.version, numpy=np.__version__,
                         cpu=platform.processor(),compute_mode=os.environ['SPEKTRAFILM_COMPUTE'],
                         gpu_user_confirmed='NVIDIA RTX 3070 Ti Laptop; actual selected adapter recorded per sample'),
        settings=dict(stock=settings.stock, paper=settings.paper, exposure=settings.exposure,
                      halation=settings.halation, varying_fields=['grain', 'grain_size', 'grain_type']),
        limits=[
            'full model at proxy: preview_mode=False retains actual grain, grain blur and DIR; only paper glare is disabled for deterministic comparison',
            'grain keeps engine fixed per-channel/sublayer seeds (offset 0), not debug stochastic deactivation; natural random noise differs if seed policy changes',
            '64px prewarm compiles/loads CPU kernels and tables but does not reach the 65536-pixel GPU eligibility threshold',
            'first per-size render is image/simulator cold; global kernels and GPU resources can remain warm from previous sizes; status is recorded before/after',
            'warm hit and miss both pay matching parameter update costs; miss removes only the source-instance exposure tap',
            'preview-only timings do not establish full-resolution export acceleration or UI frame rate; no thermal/idle isolation guarantee',
        ],
        samples=[], correctness={},
    )
    with patch('desktop.imaging.init_film_params', side_effect=deterministic_params):
        warm = original.copy()
        warm.thumbnail((64, 64), Image.Resampling.LANCZOS)
        _,prewarm_ms=milliseconds(lambda: render(warm,settings))
        report["prewarm"]=dict(dimensions=list(warm.size),ms=prewarm_ms,compute_status=compute_status())
        for edge in args.sizes:
            image = original.copy()
            image.thumbnail((edge, edge), Image.Resampling.LANCZOS)
            image._spektrafilm_preview_cache = {}
            reset_contexts()
            status_before=compute_status()
            initial,first_ms=milliseconds(lambda: render(image,settings))
            status_after_first=compute_status()
            pipeline=next(iter(imaging._SPECTRAL_CONTEXTS.values()))._pipeline
            model=dict(preview_mode=bool(pipeline.settings.preview_mode),grain_active=bool(pipeline.film_render.grain.active),
                       grain_particle_area_um2=float(pipeline.film_render.grain.particle_area_um2),
                       dir_active=bool(pipeline.film_render.dir_couplers.active),
                       dir_diffusion_size_um=float(pipeline.film_render.dir_couplers.diffusion_size_um),
                       paper_glare_active=bool(pipeline.print_render.glare.active),
                       debug_deactivate_stochastic_effects=bool(pipeline.debug.deactivate_stochastic_effects),
                       camera_film_format_mm=float(pipeline.camera.film_format_mm),
                       physical_pixel_size_um=float(pipeline._resize_service.pixel_size_um))
            tap = image._spektrafilm_spectral_stage_cache['log_e_film']
            tap_before = tap.copy()
            hit_ms, miss_ms, comparisons = [], [], []
            hit_calls = []
            changes = []
            for index in range(args.repetitions):
                changed = replace(settings, grain=28 + index, grain_size=1.1 + index*.1,
                                  grain_type='fine' if index % 2 else 'coarse')
                # Both timed paths begin at the exact same previous settings;
                # both must pay digest/update costs for the grain change.
                image._spektrafilm_preview_cache.clear()
                render(image, settings)
                with patch.object(Simulator, 'process_tap', autospec=True,
                                  side_effect=Simulator.process_tap) as observed:
                    cached, duration = milliseconds(lambda: render(image, changed))
                hit_ms.append(duration)
                hit_calls.append([dict(inject=call.kwargs['inject'], collect=call.kwargs['collect'])
                                  for call in observed.call_args_list])
                image._spektrafilm_preview_cache.clear()
                render(image, settings)
                cold_image = image.copy()
                cold_image._spektrafilm_preview_cache = {}
                # Only the cold source object's stage cache is absent.
                with patch.object(Simulator, 'process_tap', autospec=True,
                                  side_effect=Simulator.process_tap):
                    uncached, duration = milliseconds(lambda: render(cold_image, changed))
                miss_ms.append(duration)
                comparisons.append(compare(cached,uncached))
                changes.append(dict(grain=changed.grain,grain_size=changed.grain_size,grain_type=changed.grain_type,
                                    difference_from_initial=compare(initial,cached),compute_status=compute_status()))
            hit_median = statistics.median(hit_ms)
            miss_median = statistics.median(miss_ms)
            report['samples'].append(dict(
                requested_edge=edge, dimensions=list(image.size), pixels=image.width*image.height,
                cache_bytes=tap.nbytes, first_stage_miss_ms=first_ms,
                compute_status_before=status_before,compute_status_after_first=status_after_first,
                compute_status_after_warm=compute_status(),actual_digested_model=model,grain_changes=changes,
                warm_grain_change_hit_ms=hit_ms, warm_image_cache_miss_ms=miss_ms,
                hit_median_ms=round(hit_median, 4), miss_median_ms=round(miss_median, 4),
                speedup=round(miss_median/hit_median, 4),
                saved_ms=round(miss_median-hit_median, 4),
                deterministic_output_comparisons=comparisons,
                hit_calls=hit_calls,
                tap_unchanged=bool(np.array_equal(tap_before, tap)),
            ))
            print(json.dumps(report['samples'][-1]), flush=True)

        image = original.copy()
        image.thumbnail((128, 128), Image.Resampling.LANCZOS)
        render(image, settings)
        invalidation = []
        for name, changed in (
            ('exposure', replace(settings, exposure=.75)),
            ('halation', replace(settings, exposure=.75, halation=28)),
            ('stock', replace(settings, stock='kodak_ektar_100', exposure=.75, halation=28)),
        ):
            old_tap = image._spektrafilm_spectral_stage_cache['log_e_film']
            with patch.object(Simulator, 'process_tap', autospec=True, side_effect=Simulator.process_tap) as calls:
                output = render(image, changed)
            fresh = image.copy()
            fresh._spektrafilm_preview_cache = {}
            expected = render(fresh, changed)
            invalidation.append(dict(parameter=name,
                recomputed_exposure=any(c.kwargs == dict(inject='rgb_in', collect='log_e_film')
                                        for c in calls.call_args_list),
                new_tap_object=image._spektrafilm_spectral_stage_cache['log_e_film'] is not old_tap,
                comparison=compare(output, expected)))
        report['correctness']['invalidation'] = invalidation

    report['compute_status_final']=compute_status()
    report['all_correctness_checks_passed']=(
        all(sample['tap_unchanged'] and all(c['exactly_equal'] for c in sample['deterministic_output_comparisons'])
            and sample['actual_digested_model']['grain_active']
            and sample['actual_digested_model']['grain_particle_area_um2']>0
            and sample['actual_digested_model']['dir_active']
            and sample['actual_digested_model']['dir_diffusion_size_um']>0
            and not sample['actual_digested_model']['preview_mode']
            and not sample['actual_digested_model']['paper_glare_active']
            and not sample['actual_digested_model']['debug_deactivate_stochastic_effects']
            for sample in report['samples'])
        and all(c['recomputed_exposure'] and c['new_tap_object'] and c['comparison']['exactly_equal']
                for c in report['correctness']['invalidation'])
    )
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(output=str(args.output),passed=bool(report['all_correctness_checks_passed'])),ensure_ascii=False))
    if not report['all_correctness_checks_passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
