# Shapefile polygon extrusion with Dual Half Edge topology

For the **source/target transition-region workbench**, open `run_workbench.py`
in PyCharm and right-click **Run**. No parameters are needed. The local browser
window starts with all 14 requested source extrusions, unfilled. Select features
by clicking their edges or dual vertices in 3D, by clicking the small map, or by
entering IDs. Choose an operation, its winner/recipient, and an automatic or drawn
target, then click **Build transition and close DHE**. Source is at highest Z;
target is at lowest Z. Enable the slicing plane to inspect intermediate maps.

This is the current implementation of the shared symmetric-difference,
triangulation, lifting, and DHE closure pipeline. Aggregation first uses an
outward straight-skeleton partition and then an SSC merge. See
[TRANSITION_WORKBENCH.md](../TRANSITION_WORKBENCH.md) for the six construction steps,
target formats, policies, validation, and limitations. Inputs are in
`workbench_config.py`. Keep the Python run active while using the window.

The older **spaceâ€“scale generalization** examples use `run_generalization.py`
in PyCharm (right-click > Run; no parameters). It opens
`output/space_scale_generalization.html` with five operation choices and Z as
scale: simplification, merging, collapse to a polyline, collapse to a point, and
aggregation of touching features. Move the horizontal slicing plane to inspect
the intermediate map. Coverage is preserved and released area goes to 2002 in
the collapse examples. See [GENERALIZATION_DESIGN.md](../GENERALIZATION_DESIGN.md)
for the construction, policies, terminal-scale behaviour, and limitations.

The supplied `BuildingFootprintStep0.shp` was read using **osm_id = 2001, 2002**.
The source is WGS84. Both polygons are projected to a local metric azimuthal
equidistant CRS, then extruded from z=0 to **10 m**. Height is an explicit
assumption because the source has no height field. Source Z values, if any,
are ignored. The input shapefile is read only.

Open `output/extrusion_2001_2002.html` in a browser. It is self-contained and
works offline. Drag to orbit, scroll to zoom, click an edge or select a half-edge
ID to navigate. Faces begin unfilled. The height slider changes this uniform
extrusion in the viewer; rerun the script to export topology at another height.
The adjacent `.dhe.json` file stores the complete linked topology and CRS metadata.

If the app's web preview does not connect, run `.\preview.ps1` to open the
self-contained visualization directly in Edge (or the default HTML application).
You can also double-click the saved HTML in File Explorer; no server is required.

## Run directly in PyCharm

Open this folder as a PyCharm project. Use the existing `.venv` Python 3.12
interpreter, open `run_in_pycharm.py`, and right-click **Run 'run_in_pycharm'**.
No script parameters are needed. It rebuilds the model and opens the interactive
HTML in your default browser. Edit `INPUT_SHP`, `POLYGON_IDS`, `ID_FIELD`, and
`HEIGHT` at the top of that launcher to change the inputs.

## Interactive explorer

Navigation follows the DHE pointer convention used throughout this project.
These earlier examples are retained for reference and regression checks.

| Key | Action |
| --- | --- |
| F | `e = e.NF` |
| S | `e = e.S` |
| A | `e = e.D.NF.D.S` (Adjacent) |
| D | `e = e.D` |
| V | `e = e.NV` |
| O | `e = e.Adjacent().NF.Adjacent()` (PrevF) |
| E | `e = e.Adjacent().S` (NextE) |
| Z | Show current origin XYZ on screen and in the browser console |
| C | Add a translucent highlight for the current cell |
| X | Clear cell highlights |
| K | Clear current edge and vertex highlights |
| L | Clear current edge, vertex, and face highlights |
| H | Toggle primal/dual vertex labels |
| Up / Down | Move the slicing plane by 1/20 of its available range |

Each action also has a button or checkbox. Keyboard shortcuts pause while
editing inputs. Click the model before using navigation keys. Clearing an edge
highlight preserves the current topological edge, so navigation can resume.
Navigation fills only the current face (opacity 0.13); C highlights cells with
opacity 0.075. Face/cell fills are absent on initial load.

The **Attach internal dual vertices** button toggles green directed links
between existing finite dual vertices that have actual DHE connections across
shared faces. It changes display only. The display aggregates coincident dual
edge bundles between the same cell pair; individual half-edges remain selectable
by ID. All finite dual vertices remain visible, even if isolated. No inferred
nearest-neighbor links or exterior stubs are drawn. Select **Dual graph only**
to hide the primal wireframe.

Enable **Show section and slicing plane** for a horizontal Z slice. Change the
Z slider with a mouse, its scroll wheel, the Up/Down keys, or the arrow buttons.
For vertical planes, set the normal's azimuth and signed offset from the model
centre. For inclined planes, also set tilt from horizontal (0Â° horizontal,
90Â° vertical). Sections intersect the actual shell triangles/quads, stitch
segments into contours per cell, preserve holes and disconnected components,
and calculate area in the plane's orthonormal coordinates. A small 2D view shows
the section and per-cell areas. These are geometric sections, without modifying
or cutting the DHE topology. The working model is uniformly rescaled when the
extrusion slider changes; the exported JSON retains the command-line height.

The unbounded exterior has no finite dual coordinate. Navigation into it is
reported on screen; geometry requiring exterior coordinates is omitted. A dual
face/cell that cannot form a finite polygon is not filled.

Implementation: `dhe_geometry.js` contains pure navigation and intersection
functions; `viewer.js` handles interaction; `viewer.html` defines the window;
`viewer.py` embeds all scripts and topology into the offline HTML.

Additional checks:

```powershell
node test_geometry.cjs
python -m unittest -v test_section_oracle.py
# With Playwright on NODE_PATH and Microsoft Edge installed:
node test_interactive.cjs
```

## Run again

From PowerShell in this directory:

```powershell
.\run.ps1
.\run.ps1 -Ids 2001,2002 -Height 20
```

The script uses the available bundled Python runtime, with `python` as a fallback.
Dependencies are installed locally under `.deps`. On another machine:

```powershell
python -m pip install --target .deps -r requirements.txt
python extrude.py --input "C:/path/to/footprints.shp" --id-field osm_id --ids 2001 2002 --height 10 --output output/extrusion.html
python -m unittest -v test_extrude.py
```

Keep the `.shp`, `.shx`, `.dbf`, `.prj`, and optional `.cpg` sidecars together.
Supply `--source-crs EPSG:xxxx` if `.prj` is missing or needs overriding.
IDs are attribute values, not positional record numbers. A unique conventional
ID field is inferred only when all requested IDs match it unambiguously.

## DHE representation

This implementation follows the pointer/navigation convention in
[Boguslawski & Gold (2016), The Dual Half-Edge](https://doi.org/10.3390/ijgi5020019).
It constructs topology in a batch, rather than implementing the paper's general
incremental Euler operator library.

Each primal and dual half-edge stores five references:

| Reference | Meaning |
| --- | --- |
| `V` | Origin vertex; indexes primal vertices in primal space, cells/dual nodes in dual space |
| `S` | Symmetric half-edge on the same edge inside a cell |
| `NV` | Next half-edge around the origin vertex |
| `NF` | Next half-edge around a face |
| `D` | Permanently linked half-edge in the other space |

Primal half-edges occupy `[0, primal_half_edge_count)`; dual half-edges follow.
The dual is an actual linked half-edge structure: a k-sided primal face has
k associated dual half-edges, rather than a single separate adjacency record.
Explicit face/cell arrays are redundant indexes for export and rendering.
Navigation remains possible through the five half-edge references.

Cell 0 represents the unbounded exterior. Its dual node has no finite position.
The viewer omits its dual node and links. Finite dual links connect representative
points of adjacent cells; their geometry is schematic, not a Voronoi construction.

Caps are stored as complete polygonal faces. Holes use bridge edges in the NF
orbit, with separate geometric rings. A derived `render_triangles` cache handles
concavities/holes for rendering and intersection and adds no DHE edges. In the
space-scale examples, tilted transition surfaces have actual planar patches,
some triangular where a swept quad is nonplanar. Every multipart component becomes a distinct cell carrying
the same source feature ID. Common boundaries are noded before cell construction
so partially shared walls have matching faces. Coordinates are quantized at 1 Î¼m
in the topology. Exact coincident walls are sewn between cells; other faces are
paired with an exterior face.

Validation checks pointer permutations, `S.S = D.D = identity`, vertex-star and
edge-endpoint consistency, `PrevV = D.NV.D`, `PrevF = D.S.NF.D.S`, and
`Adjacent = D.NF.D.S`, plus signed shell volume against footprint area Ã— height.
The test suite covers shared walls, holes, concavity, contacts, CRS/ID handling,
and rejection of invalid input.
The section oracle also compares 90 vertical/inclined cuts against independent
Shapely footprint intersections, including courtyard-wall coincidences.

Scope: valid polygon/multipolygon footprints, one uniform positive height and
flat base, no overlapping interiors, no general Boolean solid operations or
incremental Euler editing. Invalid polygons are reported rather than repaired
silently. This local projection is intended for compact datasets, such as these
building footprints, rather than global or antimeridian-spanning polygons.
This paragraph describes the original extrusion constructor; the additional
space-scale constructions and their separate scope are documented in
`GENERALIZATION_DESIGN.md`.
