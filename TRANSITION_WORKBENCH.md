# Source / target transition-region workbench

## Run in PyCharm

For a portable first run, open `run_demo.py` and choose **Run**. It uses fourteen
original synthetic footprints and requires no shapefile. To use your own input,
copy `workbench.local.example.json` to `workbench.local.json`, set `input_shp`,
and edit the IDs in `workbench_config.py`. The local settings file is ignored by Git.
You can also set the `DHE_INPUT_SHP` environment variable. Without an input path,
`run_workbench.py` automatically uses the synthetic demo. `--demo` forces it.

1. Open this project and select its `.venv\Scripts\python.exe` interpreter.
2. Open `run_workbench.py`, right-click, and choose **Run**. No script parameters
   are required. A local browser window opens automatically.
3. Keep that Python run active. Use **Stop** in PyCharm to stop the server.

The project already has the required packages in `.deps`. On a fresh checkout,
install `requirements.txt` into the selected interpreter:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The application runs on a loopback URL printed as `DHE_WORKBENCH_URL=...` in the
Run console. Open that URL in Edge or another browser if the embedded Web preview
does not work. Building new operations requires the running Python backend;
opening the generated HTML with `file://` supports viewing only.

`workbench_config.py` loads `BuildingFootprintStep0.shp` using `osm_id`, with:

```python
FEATURE_IDS = [20, 2001, 2002, 8, 9, 17, 18, 21, 1123,
               3000, 3001, 3002, 3003, 3004]
SOURCE_Z = 10.0
TARGET_Z = 0.0
```

XY is projected into a local metric CRS; Z represents scale. The input shapefile
is read only. Feature IDs are configurable and are not hard-coded in the
construction algorithms.

## Choose sources and targets

All source cells initially appear as unfilled wireframes with finite dual
vertices. Click an edge or dual vertex to add/remove its feature from selection,
or use the small map or the comma-separated ID field. Disable **Pick features
in 3D** when navigating without changing the operation selection.

| Operation | Sources | Target |
| --- | --- | --- |
| Simplification | One | Automatic simplified polygon with adjustable tolerance, or supplied polygon |
| Merge | Two or more edge-adjacent sources | Chosen winner receives the union; each loser ends as a point, interior polyline, or its source boundary |
| Collapse to point | One | Automatic interior point, or any supplied point covered by the source |
| Collapse to polyline | One | Automatic internal triangulation edge, or a supplied polyline covered by the source |
| Aggregation | Two or more | Convex hull of the selected union by default, or a supplied covering polygon |
| Custom polygon target | One | Any valid polygon or multipolygon target |

Use **Pick point**, **Draw polyline**, or **Draw polygon** on the small map.
Finish a line/polygon with **Finish target**. **Clear target** restores automatic
target generation. You can instead paste WKT or a GeoJSON geometry into the
target field. Coordinates must be in the displayed local XY metres, not longitude
and latitude. A collapse target may touch the source boundary.

For several merge losers, supply JSON keyed by feature ID, with WKT or GeoJSON
geometry values. For example, with winner 3000 and two selected losers:

```json
{"3001": "POINT (x1 y1)", "3002": "POINT (x2 y2)"}
```

Replace the illustrative coordinates with points inside those sources. A single
target supplied for a two-source merge applies to the loser. The loser target
type must match the selected loser mode. The winner's target is always the union.

Every build uses the loaded original source map and the current selection.
**Reset source extrusions** restores that initial map in the viewer.

## One construction for all operations

Only target generation is operation-specific (`target_geometry.py`). All
operations call `build_transition` in `transition_regions.py`:

1. **Source and target maps.** Source caps occupy the highest Z and target caps
   the lowest Z. Ownership includes unselected neighbours and the exterior cell.
2. **Transition regions.** Compute each feature's symmetric difference
   `(S − T) ∪ (T − S)`. Points and lines have zero area, so their subtraction does
   not remove area from a polygon: insert them explicitly as target constraints.
3. **Planar DHE faces.** Insert transition polygons, including their hole rings,
   into a DHE construction face pool at source Z. These are open construction
   faces at this stage, before shell sewing.
4. **Conforming triangulation.** Node the combined source/target boundaries and
   symbols in one planar straight-line graph, then constrain-triangulate it with
   Triangle. This gives both sides of every shared interface the same vertices.
5. **Lift the transition.** Assign heights using distance to the source boundary
   `ds` and target constraints `dt`:
   `z = targetZ + (sourceZ − targetZ) × dt / (ds + dt)`.
   Interpolate linearly within each constrained triangle. Source-only boundary
   vertices are at source Z; target-only constraints are at target Z. Lower-rank
   point/line constraints take priority. Coincident source/target vertices use
   intermediate Z, with closure curtains retaining both endpoint maps.
6. **Close and refine.** Form owner-labelled wedges above/below the lifted field,
   remove internal faces, splice coplanar faces with KEF, remove dispensable
   collinear vertices with KVE, and rebuild closed linked primal/dual shells.
   Explicit edge-fan sewing retains the non-manifold structure at terminal ridges.

For aggregation's first stage, substitute the skeleton-interface Z for target Z
in step 5. Faces use polygon boundary loops after coplanar refinement. The
original roof/base caps remain polygon faces; the transition surfaces contain the
triangles required by this construction. A separate triangle cache supports
rendering and arbitrary-plane intersection without changing DHE face navigation.

The final model uses actual `V`, `S`, `NV`, `NF`, and `D` links. Validation checks
closed face/cell orbits, inverse pointers, origin consistency, adjacency and dual
identities, positive shell volumes, and agreement with an independent integral
over the construction wedges. This is a batch constructor with boundary surgery;
half-edge numeric IDs are regenerated after each build.

## Neighbours and coverage

Every planar triangle has one source owner and one target owner. A transfer
therefore creates one shared transition interface for both cells. Neighbours
follow it automatically, without independently interpolating overlapping shells.

For simplification/custom targets, expanded area is removed from existing
owners. Released source area goes to the chosen adjacent recipient, or the
adjacent feature with the longest shared boundary. Collapse uses the same
recipient policy. If there is no adjacent loaded feature, released area goes to
the exterior; this is reported in the window. Background is part of the coverage
model, so an isolated building can disappear without inventing a neighbouring
building. The union of finite feature areas need not stay constant in that case.

Merging requires an edge-connected selected set. Aggregation can bridge gaps.
An aggregation target can cover unselected features; their covered portions are
transferred to the aggregate and the window reports the affected IDs. Select the
intended sources and inspect the target outline before interpreting that result.

## Two-stage aggregation

`skeleton_partition.py` uses **py_straight_skeleton 0.1.0**. Selected source union
components become holes in an enclosing frame. Their hole wavefronts propagate
outwards into the transition gap. Skeleton faces retain the originating source
edge's ownership. Courtyard voids are processed as separate inward wavefront
domains. Clip the faces to the requested target and check that frame-owned faces
do not enter it. Check coverage and overlap before accepting the partition.

Stage 1 smoothly transfers each source polygon into its outward skeleton
partition. Stage 2 is classic SSC: a horizontal interface ends the partition
cells, and the winner continues below it as their union. It is a discrete merge
event at the interface, while the expansion above it is continuous. The default
interface is halfway between source and target Z; it is adjustable.

The implementation does not substitute a Voronoi partition if the straight
skeleton fails. A failed wavefront or invalid partition produces an explicit
construction error.

## Inspect and export

The **Construction layer** selector shows transition-region faces at source Z,
the flat triangulation, the lifted transition mesh, or the skeleton interface.
These layers are optional inspection overlays; initial face/cell fills are off.
Selections and navigation use very translucent fills.

Enable **Show section and slicing plane**. Up/Down, the slice slider, or scrolling
over that slider changes horizontal Z. Vertical and inclined planes remain
available. At an event level, descending-scale ownership uses the lower-Z side;
closed endpoint caps use their geometric face rings. Point and line terminals
are displayed as lower-dimensional sections with zero area. The first view starts
at source Z. Z scaling in the viewer is visual; rebuild to change exported levels.

Existing DHE keys F/S/A/D/V/O/E, face/cell highlighting, labels, and dual graph
controls remain available. **Attach internal dual vertices** shows green links
only for actual DHE connections; isolated finite dual vertices remain visible.

**Export current DHE** downloads JSON with the final topology, maps, transition
construction, and skeleton diagnostics. The last constructed model is also saved
to `output/workbench/latest.dhe.json`.

## Validation and current limits

`test_unified.py` checks arbitrary point/bent-line targets, boundary targets,
holes, both merge winners, symmetric-difference regions, source/target endpoint
maps, invalid inputs, and real operations across the 14-feature context. It
compares intermediate shell sections against independent 2D clipping of the
lifted field, including exact event/interface levels. Existing tests additionally
check navigation, solid construction, arbitrary planes, and legacy operations.
`test_workbench.cjs` exercises the live browser/backend flow and drawing controls.

Geometry is canonicalized to a one-micrometre grid in projected metres. Triangle
intersections are re-noded at that precision before lifting. This is a research
implementation: particularly degenerate skeleton inputs can be rejected, and
separate enclosed cavity shells requiring a cavity bridge are currently rejected.
Targets must be valid; automatic collapse lines are simple internal edges, not a
full road-axis extraction method. No perceptual/cartographic objective is
optimized beyond the chosen target and distance-based lifting rule. The original
GitHub repository is unchanged; this work lives in the local project.
