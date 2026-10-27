"""Public common-operation API, independent of feature IDs and input targets."""
from dataclasses import replace
from target_geometry import plan_targets,polygonal
from transition_regions import build_transition
from skeleton_partition import outward_partition


def generalize(source,operation,selected,*,winner=None,target=None,targets=None,tolerance=2.5,
               loser_kind='point',recipient=None,z_low=0,z_high=10,interface_z=None):
    plan=plan_targets(source,operation,selected,winner,target,targets,tolerance,loser_kind,recipient)
    if operation!='aggregation':return build_transition(plan,z_low,z_high)
    hull=plan.requested[plan.winner]
    partitions,skeleton=outward_partition({i:source[i] for i in plan.selected},hull)
    intermediate=dict(plan.target)
    intermediate.update(partitions)
    stage=replace(plan,target=intermediate)
    model,info=build_transition(stage,z_low,z_high,classic_target=plan.target,
                              interface_z=interface_z if interface_z is not None else (z_low+z_high)/2)
    info['skeleton']=skeleton
    return model,info
