## 1. Backend orientation contract

- [x] 1.1 Add a shared backend normalizer for `viewer_orientation` (`default`, `y-front`, `unknown`) with conservative handling for missing or invalid values, and keep coordinate-system facts separate from preview instructions.
- [x] 1.2 Write `viewer_orientation: default` into successful image-generation sidecars and `viewer_orientation: y-front` into successful video-reconstruction sidecars without modifying existing model files.
- [x] 1.3 Project `viewer_orientation` and trusted `source_media_type` through generated/imported model-asset summaries, details, recent items, and every companion-format descriptor; represent unclassified imports as `unknown`.
- [x] 1.4 Reuse the existing conservative legacy-video recovery only during controlled index refresh/rebuild, derive Y-front only from unique trusted evidence, and verify ordinary warm pagination does not rescan source media.

## 2. Frontend model context and resolution

- [x] 2.1 Synchronize frontend API/types with the optional orientation fields and implement a pure `viewerOrientation` resolver that applies explicit-hint, trusted-source, legacy, and unknown fallback precedence without reading bounds or file extensions.
- [x] 2.2 Replace the positional current-model setter with a typed `CurrentModelDescriptor` carrying stable ID, URL, format, size, source, source media type, and orientation hint while preserving existing localStorage v1 Quick Controls overrides.
- [x] 2.3 Update asset list/recent/detail/sidebar, companion-format selection, generated-model completion, imported-model completion, temporary Blob preview, settings reload, and retained gallery compatibility entry points to pass the complete descriptor.
- [x] 2.4 Remove Viewer orientation dependence on `galleryItems` lookup and ensure clearing, switching, and reloading the active model also clear or replace its resolved orientation context atomically.

## 3. Viewer, transforms, and diagnostics

- [x] 3.1 Resolve orientation once for each active load, bind the result and reason to that load's Viewer context, and apply the existing Y-front quaternion only for a resolved `y-front` model.
- [x] 3.2 Remove the AABB depth-ratio Y-front heuristic and any reset-time orientation mutation while retaining bounds-based target, centering, fit-distance, and unavailable-bounds fallback behavior.
- [x] 3.3 Preserve the existing `source correction × user transform` quaternion order, keep hidden source correction out of persisted overrides, and enforce the specified camera-reset, orientation-reset, and reset-all semantics.
- [x] 3.4 Guard orientation, bounds, framing, and debug commits with the current load generation so a superseded or cancelled image/video load cannot update the next model.
- [x] 3.5 Split the debug reading into orientation mode/reason and framing mode, update copied debug text, and add matching user-visible labels to both `frontend/src/i18n/en.json` and `frontend/src/i18n/zh.json`.

## 4. Automated verification

- [x] 4.1 Add backend pytest coverage for new image/video sidecars, list/detail orientation projection, imported unknown fallback, safe legacy-video recovery, warm-page behavior, and PLY/SPZ companion consistency.
- [x] 4.2 Add `frontend/src/utils/viewerOrientation.test.ts` to the existing lightweight `node:test` workflow, with cases for precedence, invalid/missing values, flat image bounds independence, verified video, imports, and stable asset identity across formats.
- [x] 4.3 Add focused state/transform regression coverage for saved user overrides, repeated reset, image → video → image switching, format reload, and superseded-load isolation without introducing a new test framework.
- [x] 4.4 Run the focused frontend Node tests and backend pytest files, then run frontend lint and production build; resolve all failures without modifying `ml-sharp/`, `templates/`, or `static/lib/`.

## 5. Manual regression and acceptance

- [x] 5.1 Open `img-7f18fe7dd29e4890987eab0b49313ca8.spz` and confirm it remains on the image/default baseline despite its former matching bounds ratio, then verify `img-0844e14c4e904c34b80901434957d0ac.spz` has no visual regression.
- [x] 5.2 Open one verified video reconstruction in both PLY and SPZ, confirm the existing Y-front model correction remains, camera up is `+Y`, initial orbit polar stays away from a pole, and both formats share the same user override.
- [x] 5.3 Verify imported, temporary Blob, ambiguous legacy, and safely recovered legacy-video models follow their specified unknown/default or Y-front policies and retain usable manual Quick Controls presets.
- [x] 5.4 Exercise rapid image/video switching, cancelled loads, repeated camera reset, orientation reset, reset all, reopen, and format switching; confirm no direction accumulates or leaks and the bilingual diagnostics report orientation separately from framing.
- [x] 5.5 Review the final diff and OpenSpec scenarios to confirm every model-opening path and reset behavior is covered, no historical sidecars/models were bulk rewritten, and all changes remain inside the React Viewer/model-asset/backend service scope.
