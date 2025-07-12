# /// script
# dependencies = [
#   "pandas",
#   "plotly[express]",
# ]
# ///

import argparse
import pandas as pd
import plotly.express as px

# TODO: read from standard in
parser = argparse.ArgumentParser()
parser.add_argument(
    "input",
    type=str,
    help="A schedule input file specifying a job's period, processing time, release time, due date, and start time.",
)
args = parser.parse_args()

input_schedule_csv = args.input
jobs = pd.read_csv(input_schedule_csv)

# Ensure the name is a string
jobs["name"] = jobs["name"].apply(lambda value: str(value))

# Add completion times for each job
jobs["completion_time"] = jobs["start_time"] + jobs["processing_time"]


# Create the schedule with the periodic jobs
def create_job_instances(record):
    job_instances = pd.DataFrame()
    for instance_idx in range(int(record["instances"])):
        job_instance = pd.DataFrame(record).transpose()
        job_instance["release_time"] = (
            instance_idx * job_instance["period"] + job_instance["release_time"]
        )
        job_instance["due_date"] = (
            instance_idx * job_instance["period"] + job_instance["due_date"]
        )
        job_instance["start_time"] = (
            instance_idx * job_instance["period"] + job_instance["start_time"]
        )
        job_instance["completion_time"] = (
            instance_idx * job_instance["period"] + job_instance["completion_time"]
        )
        job_instance["machine"] = str(1)
        job_instances = pd.concat([job_instances, job_instance], ignore_index=True)
    return job_instances


schedule_series = jobs.apply((create_job_instances), axis="columns")
schedule_list = schedule_series.tolist()
schedule = pd.concat(schedule_list, ignore_index=True)

fig = px.bar(
    schedule,
    base="start_time",
    x="processing_time",
    y="machine",
#    error_x=dict(
#        type="data",
#        symmetric=False,
#        array=(schedule["due_date"] - schedule["completion_time"]).tolist(),
#        arrayminus=(schedule["start_time"] - schedule["release_time"]).tolist(),
#    ),
    color="name",
    orientation="h",
    opacity=0.7,  # have some opacity to show overlap
)

# Add range slider
fig.update_layout(xaxis=dict(rangeslider=dict(visible=True), type="linear"))

# Here is an example in matplotlib with possible time interval
# https://github.com/d-krupke/cpsat-primer?tab=readme-ov-file#scheduling-and-packing-with-intervals
# show conflicts

# show precedence relations
# idea, when clicking on a particular job instance, show the predecessor job instances for it and the successor job instances for it (kind of like a graph)
# can also expand to show the successor's successors and the predecessor's predecessors
# This would be a really neat visualization and help show the job dependency graph
# Could even help identify if a job needs to run at a particular period?
# Or if sporadic instances of the job can be removed from the schedule
# To extrapolate this information, the solver can tell us and we can include in our output
# something like predecessor_instance: [1, 3, 45], where the list represents the predecessor job instance for the first successor job instance
# What about the other successor job instances? It would require us to output all instances of the successor jobs... futurework i guess

# have filters such as period group

# Add dropdown for period
# import pdb; pdb.set_trace()
# period_buttons = [dict(label=str(period), args=[], method="update") for period in schedule["period"].unique()]

# Do I want to remove the other period data when displaying or decrease the opacity? Decreasing the opacity still keeps context if needed.
# import pdb; pdb.set_trace()

# fig.update_layout(
#    updatemenus=[
#        dict(
#            buttons=list(
#                [
#                    dict(
#                        args=["type", "surface"], label="3D Surface", method="restyle"
#                    ),
#                    dict(args=["type", "heatmap"], label="Heatmap", method="restyle"),
#                ]
#            ),
#            direction="down",
#            pad={"r": 10, "t": 10},
#            showactive=True,
#            x=0.1,
#            xanchor="left",
#            y=1.1,
#            yanchor="top",
#        ),
#    ]
# )

fig.show()
