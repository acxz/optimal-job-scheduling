# /// script
# dependencies = [
#   "pandas",
#   "plotly[express]",
# ]
# ///

import argparse
import sys
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

parser = argparse.ArgumentParser()
parser.add_argument(
    "schedule",
    type=str,
    nargs="?",
    default="-",  # use "-" to denote stdin by convention
    help="csv of jobs specifying their characteristics via stdin or specified as a file.",
)
args = parser.parse_args()

schedule_file = sys.stdin if args.schedule == "-" else args.schedule
jobs = pd.read_csv(schedule_file)

# Ensure the job_name is a string
jobs["job_name"] = jobs["job_name"].apply(lambda value: str(value))


# Populate a schedule with periodic job instances
def create_job_instances(record):
    job_instances = pd.DataFrame()

    instance_idx_range = range(int(record["instances"]))
    # If a job wraps around its period, plot another job instance that captures the job instance in the previous period
    if record["completion_time"] < record["start_time"]:
        # Ensure that the range includes a negative 1 instance index to capture the instance from the previous period
        instance_idx_range = range(-1, int(record["instances"]))

    for instance_idx in instance_idx_range:
        job_instance = pd.DataFrame(record).transpose()
        job_instance["instance"] = instance_idx + 1
        job_instance["start_time"] = (
            instance_idx * job_instance["period"] + job_instance["start_time"]
        )
        job_instance["completion_time"] = (
            job_instance["start_time"] + job_instance["processing_time"]
        )
        job_instance["release_time"] = (
            instance_idx * job_instance["period"] + job_instance["release_time"]
        )
        job_instance["deadline"] = (
            instance_idx * job_instance["period"] + job_instance["deadline"]
        )
        job_instances = pd.concat([job_instances, job_instance], ignore_index=True)
    return job_instances


schedule_series = jobs.apply((create_job_instances), axis="columns")
schedule_list = schedule_series.tolist()
schedule = pd.concat(schedule_list, ignore_index=True)

# Manually set colors
colors = px.colors.qualitative.Plotly
color_idx = 0

# Create traces for each job
traces = []
for job_name in schedule["job_name"].unique():
    job_schedule = schedule[schedule["job_name"] == job_name]

    traces.append(
        go.Bar(
            name=job_name,
            text=job_name,
            base=job_schedule["start_time"],
            x=job_schedule["processing_time"],
            y=job_schedule["machine_name"],
            error_x=dict(
                type="data",
                symmetric=False,
                array=None
                if job_schedule["earliness"].isnull().all()
                else job_schedule["earliness"],
                arrayminus=None
                if job_schedule["flow_time"].isnull().all()
                else job_schedule["flow_time"],
            ),
            hovertemplate="instance=%{customdata[6]}<br>"
            + "start_time=%{customdata[7]}<br>"
            + "completion_time=%{customdata[8]}<br>"
            + "release_time=%{customdata[9]}<br>"
            + "deadline=%{customdata[10]}<br>"
            + "<extra>"
            + "job_name=%{customdata[0]}<br>"
            + "period=%{customdata[1]}<br>"
            + "processing_time=%{customdata[2]}<br>"
            + "flow_time=%{customdata[3]}<br>"
            + "earliness=%{customdata[4]}<br>"
            + "machine_name=%{customdata[5]}"
            + "</extra>",
            customdata=job_schedule[
                [
                    "job_name",
                    "period",
                    "processing_time",
                    "flow_time",
                    "earliness",
                    "machine_name",
                    "instance",
                    "start_time",
                    "completion_time",
                    "release_time",
                    "deadline",
                ]
            ],
            orientation="h",
            opacity=0.5,  # have some opacity to show overlap
            marker_color=colors[
                color_idx
            ],  # specify colors manually to match error colors
        )
    )
    color_idx = color_idx + 1

# Create button for showing/hiding time constraints
time_constraint_button = dict(
    label="Toggle Time Constraints",
    method="restyle",
    args=[{"error_x.visible": True}],
    args2=[{"error_x.visible": False}],
)
time_constraint_menu = dict(
    type="buttons", buttons=[time_constraint_button], yanchor="bottom"
)

# Create a dropdown for showing jobs grouped by period
# For reference: https://stackoverflow.com/questions/65941253/plotly-how-to-toggle-traces-with-a-button-similar-to-clicking-them-in-legend
period_buttons = []
for period in schedule["period"].unique():
    period_schedule = schedule[schedule["period"] == period]

    # Create a button for showing jobs only with a particular period/showing all jobs
    period_buttons.append(
        dict(
            label="Toggle All/Period: " + str(period),
            method="restyle",
            args=[
                {
                    "visible": [
                        True
                        if (trace.customdata[:, 1] == period).all()
                        else "legendonly"
                        for trace in traces
                    ]
                }
            ],
            args2=[
                {"visible": True},
                [trace_idx for trace_idx, trace in enumerate(traces)],
            ],
        )
    )

    # Create a button for showing/hiding jobs grouped by period
    period_buttons.append(
        dict(
            label="Toggle Period: " + str(period),
            method="restyle",
            args=[
                {"visible": True},
                [
                    trace_idx
                    for trace_idx, trace in enumerate(traces)
                    if (trace.customdata[:, 1] == period).all()
                ],
            ],
            args2=[
                {"visible": "legendonly"},
                [
                    trace_idx
                    for trace_idx, trace in enumerate(traces)
                    if (trace.customdata[:, 1] == period).all()
                ],
            ],
        )
    )

period_menu = dict(type="dropdown", buttons=period_buttons)

layout = go.Layout(
    title_text="Schedule",
    legend_title_text="Job",
    xaxis_title_text="Time",
    yaxis_title_text="Machines",
    barmode="overlay",  # overlay each job to visualize conflicts if any
    xaxis=dict(rangeslider=dict(visible=True), type="linear"),  # add range slider
    # Add menus for time constraints and jobs grouped by period
    updatemenus=[time_constraint_menu, period_menu],
)

fig = go.Figure(data=traces, layout=layout)

# Match colors of each job's time constraints with the job's color if specified
fig.for_each_trace(
    lambda trace: trace.update(error_x_color=trace["marker"]["color"])
    if trace["marker"]["color"] is not None
    else ()
)

fig.show()
