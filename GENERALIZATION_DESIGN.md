# Current workbench

The current source-at-highest-Z implementation is described in
[TRANSITION_WORKBENCH.md](TRANSITION_WORKBENCH.md). Run `run_workbench.py` for the
14-feature selection window, arbitrary targets, common transition construction,
and two-stage straight-skeleton aggregation. The document below describes the
earlier fixed demonstrations, which remain available as regression examples.

# DHE space-scale generalization

## Run and inspect

Run `run_generalization.py` in PyCharm. It opens
`output/space_scale_generalization.html` with five selectable operations.
Z is a dimensionless scale parameter, not building height or animation time.
Horizontal sections are intermediate 2D maps; vertical/inclined sections inspect
the space-scale structure. Each construction is also exported as
`output/<operation>.ssc.dhe.json` with complete primal/dual incidence and lineage.

## Polygon faces and transition geometry

The extrusion foundation now stores one complete polygon roof and base per
footprint component. Hole rings are connected by reversible bridge edges in NF.
The `render_triangles` cache creates no topological edges and is never the face
identity used for navigation.

Space-scale construction introduces genuine new event surfaces. A swept boundary
quad can be nonplanar; the implementation splits that surface into exact planar
patches, choosing the same diagonal on both incident cells. Collapse uses a
piecewise-linear terrain, whose noncoplanar facets are actual faces. These
triangular transition faces are distinct from arbitrarily triangulating an
original horizontal map cap, which remains a polygon.

## Shared-boundary simplification

`dhe_ops.Generalizer` proposes degree-two boundary-column suppression events.
It protects junctions and hole-bridge endpoints and checks boundary Hausdorff
error for every incident cell. One shared coordinate is moved for all owners;
neighbour geometry is not simplified independently. The geometric motion checks
all intervals delimited by linear edge-orientation predicates, at floating-point
precision, and rejects invalid/overlapping polygons.

At an event, the two incident wall faces are joined, their common vertical edge
is removed, and the collinear roof/base vertex is suppressed in every incident
cell. The edited polygon loops are compacted and the complete primal/dual
incidence is re-sewn and validated. This is a transactional reference
implementation, not in-place execution of the GitHub KEF/KVE functions.

`space_scale.simplify_space_scale` sweeps these events into one 3D cell per
feature. An additional plateau resolves the final event and closes the complex.
For fixed bounded coverage, the outer envelope is locked. On the provided data,
the 2.5 m tolerance removes one shared corner: 2001 has 23 -> 22 boundary vertices,
and 2002 automatically has 8 -> 7. The event completes at scale Z=5 in [0,10].
This deliberately does not simplify the outside outline while claiming to keep
the same bounded coverage.

The earlier `run_simplification.py` remains a separate geometry-preview example:
it permits exterior outline changes and gives 23 -> 11 vertices. Its t slider
is not the space-scale model and is not the coverage-preserving default.

## Merging and touching aggregation

Below Z=5, the original feature cells occupy their original map regions.
Above Z=5, a new merged cell occupies their exact union. Its lower boundary has
one polygon face per predecessor, preserving valid shared horizontal faces and
primal/dual links. Existing neighbours have their scale patches split and sewn
to the correct predecessor/successor. Source cells use half-open upper scale
intervals so a section exactly at the event does not double-count map area.

Aggregation implements the chosen touching-feature policy using the same exact
union construction with an aggregation identity/lineage. It rejects a selected
set that is not connected through shared boundaries; it does not bridge gaps or
buffer unrelated objects. Geometry is continuous; the identity/incidence event
is discrete. Pointer values are never interpolated.

## Polygon-to-polyline and polygon-to-point collapse

The source footprint has a piecewise-linear scale-height field. A constrained
mesh is used as a geometric support for this field. Graph distance from the
terminal root gives a field with a unique maximum point, or a connected maximum
edge. The source SSC cell lies below this terrain. Above it, released area
belongs to the selected adjacent recipient. This construction keeps the union
fixed at every scale, works with concavities/holes, and does not shrink a polygon
through the exterior or approximate a line with an epsilon-width polygon.

For the demonstration, 2001 is the source, 2002 the recipient, the terminal
scale is Z=9, and the complex closes with a recipient plateau up to Z=10.
The point target is an interior support-triangle centroid. The line target is
one internal support edge; it is a valid two-vertex polyline, not a computed
cartographic medial axis. Both targets are recorded in metadata. The terminal
point/edge is present in the DHE itself and in the section at Z=9. Above Z=9,
the source is absorbed into the recipient. Persistent line/point cartographic
symbols for ALL coarser scales are not yet represented as separate dangling
carrier cells. Such persistence would require a further mixed-dimensional
extension; the implementation does not silently claim that a terminal marker
is that extension.

A specified recipient must share a source boundary. If none is specified, the
largest shared-boundary neighbour is chosen. Other represented neighbours keep
their map geometry but have source/recipient interface patches re-sewn at the
correct scale. Source and recipient cannot be the same feature. Collapse is
currently defined for one polygon component at a time.

## Precision, units, and validation

XY coordinates are metres; Z is a scale parameter. Horizontal section areas are
m2. SSC volume is m2 * scale. Inclined/vertical section areas use the numerical
plotted coordinates and are labelled plot units2, not physical square metres.
Vertices are stored at 1e-6 coordinate precision; incidence noding uses 2e-6 to
handle collinear event projections consistently.

All five examples check pointer permutations, S/D involutions, NF/NV/Adjacent
identities, shell closure and signed volume. Collapse/merge volumes are also
compared with independent area/terrain integrals. Tests check area coverage on
both sides of events and exactly at critical planes, including true terminal
line/point sections, holes, and a third adjacent feature. The browser checks
operation switching, slicing, navigation, scale labels, and coverage.

The constructors are batch space-scale event constructions. They do not yet
provide a persistent-ID in-place Euler editor, automatic chaining of arbitrary
operations into one history, inverse operators, geometric optimality, arbitrary
collapse target polylines, or a full exact-predicate non-manifold geometry kernel.
The chosen simplification path is piecewise linear (C0 continuous), not a C1
spline. Existing Python/GitHub files are not modified remotely.

Automatic propagation covers represented cells. The supplied 2001 footprint
has only 2002 as a touching neighbour in the source shapefile. For other inputs,
load all relevant neighbours; unmodelled neighbours cannot be updated.

Reference: [Boguslawski & Gold (2016), The Dual Half-Edge](https://doi.org/10.3390/ijgi5020019).
