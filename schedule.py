# /// script
# dependencies = [
#   "ortools",
# ]
# ///

from ortools.sat.python import cp_model
import argparse
import ast
import csv
import math
import sys

parser = argparse.ArgumentParser()
parser.add_argument(
    "input",
    type=str,
    nargs="?",
    default="-",  # use "-" to denote stdin by convention
    help="csv of jobs specifying their characteristics. If all start times are specified, then the start times are checked for.",
)
args = parser.parse_args()
input_schedule_file = sys.stdin if args.input == "-" else open(args.input)
reader = csv.DictReader(input_schedule_file)

# TODO: create a dictionary of dicts, iterate via .items()
jobs = []

has_period = "period" in reader.fieldnames
has_processing_time = "processing_time" in reader.fieldnames
has_release_time = "release_time" in reader.fieldnames
has_deadline = "deadline" in reader.fieldnames
has_start_time = "start_time" in reader.fieldnames
has_predecessors = "predecessors" in reader.fieldnames
has_slack_times = "slack_times" in reader.fieldnames
has_time_lags = "time_lags" in reader.fieldnames
has_completion_time_weight = "completion_time_weight" in reader.fieldnames
has_flow_time_weight = "flow_time_weight" in reader.fieldnames
has_earliness_weight = "earliness_weight" in reader.fieldnames

for row in reader:
    predecessors = (
        ast.literal_eval(row["predecessors"])
        if has_predecessors and row["predecessors"] != ""
        else None
    )
    # if no slack time specified assume infinite slack (i.e. None)
    # If two predecessors, but only one has a slack time
    # specify slack_times as [None, 10] in input
    slack_times = (
        ast.literal_eval(row["slack_times"])
        if has_slack_times and row["slack_times"] != ""
        else [None] * len(predecessors)
        if predecessors is not None
        else None
    )
    # If two predecessors, but only one has a time lag
    # specify time_lags as [0, 10]
    # If there are predecessors the default is a list of zeros
    # as the time lag is used in the precedence constraint
    # If time lags constraints were separate from the precedence constraint,
    # then negative time lags (i.e. time leads) would conflict with the
    # precedence constraint
    # Hence the precedence and the time lag constraint are fused together
    time_lags = (
        ast.literal_eval(row["time_lags"])
        if has_time_lags and row["time_lags"] != ""
        else [0] * len(predecessors)
        if predecessors is not None
        else None
    )

    # Error handling for precedence relations
    is_precedence_input_inconsistent = False
    if predecessors is None:
        if slack_times is not None:
            print(
                "Slack times must not be specified when predecessors are not specified!",
                file=sys.stderr,
            )
            is_precedence_input_inconsistent = True
        if time_lags is not None:
            print(
                "Time lags must not be specified when predecessors are not specified!",
                file=sys.stderr,
            )
            is_precedence_input_inconsistent = True
    else:
        if slack_times is not None and len(predecessors) != len(slack_times):
            print(
                "Number of slack times must equal number of predecessors or remain unspecified!",
                file=sys.stderr,
            )
            is_precedence_input_inconsistent = True
        if len(predecessors) != len(time_lags):
            print(
                "Number of time lags must equal number of predecessors or remain unspecified!",
                file=sys.stderr,
            )
            is_precedence_input_inconsistent = True

    if is_precedence_input_inconsistent:
        sys.exit()

    job = {
        "name": row["name"],
        # Period must be specified
        "period": int(row["period"]),
        "start_time": int(row["start_time"])
        if has_start_time and row["start_time"] != ""
        else None,
        "processing_time": int(row["processing_time"])
        if has_processing_time and row["processing_time"] != ""
        else 1,
        "release_time": int(row["release_time"])
        if has_release_time and row["release_time"] != ""
        else None,
        "deadline": int(row["deadline"])
        if has_deadline and row["deadline"] != ""
        else None,
        "predecessors": predecessors,
        "time_lags": time_lags,
        "slack_times": slack_times,
        "completion_time_weight": int(row["completion_time_weight"])
        if has_completion_time_weight and row["completion_time_weight"] != ""
        else 0,
        "flow_time_weight": int(row["flow_time_weight"])
        if has_flow_time_weight and row["flow_time_weight"] != ""
        else 0,
        "earliness_weight": int(row["earliness_weight"])
        if has_earliness_weight and row["earliness_weight"] != ""
        else 0,
        # variable to solve for
        "start_time_var": None,
    }
    jobs.append(job)

# Compute the hyper-period of the schedule
periods = [jobs[idx]["period"] for idx in range(len(jobs))]
hyper_period = math.lcm(*periods)

# Obtain the number of instances for each job in the hyper-period
for idx in range(len(jobs)):
    job = jobs[idx]
    job["instances"] = hyper_period // job["period"]

model = cp_model.CpModel()

# Interval variables used to check for no overlap
interval_vars = []

for idx in range(len(jobs)):
    job = jobs[idx]
    # Ensure the job starts on a valid bound
    # Bound is tighter than hyper_period - job['processing_time']
    # since we do not wrap a job to the next cycle, a job instance cannot
    # wrap across its period either
    if job["start_time"] is None:
        job["start_time_var"] = model.new_int_var(
            0,
            job["period"] - job["processing_time"],
            f"job_{idx}_start_time",
        )
    # If the start time is specified then ensure the start time is respected
    else:
        job["start_time_var"] = model.new_constant(job["start_time"])

    # Ensure the release time and deadline are respected
    # In this context of periodicity, release time and deadline are defined as
    # a time within the job's first period
    if job["release_time"] is not None:
        model.add(job["start_time_var"] >= job["release_time"])

    if job["deadline"] is not None:
        model.add(job["start_time_var"] + job["processing_time"] <= job["deadline"])

    for instance_idx in range(job["instances"]):
        # An interval variable for each instance of the job during the cycle is
        # created to ensure no interval overlap
        job_instance_interval_var = model.new_fixed_size_interval_var(
            job["start_time_var"] + instance_idx * job["period"],
            job["processing_time"],
            f"job_{idx}_instance_{instance_idx}_interval",
        )
        interval_vars.append(job_instance_interval_var)

model.add_no_overlap(interval_vars)

# To add precedence constraints run a second pass through the jobs
# to ensure all the jobs' start time variables have been created
for successor_idx in range(len(jobs)):
    successor_job = jobs[successor_idx]

    # Ensure the precedence relations are respected
    if successor_job["predecessors"] is not None:
        for predecessor_idx in range(len(successor_job["predecessors"])):
            # FIXME, this could be better by making jobs a dictionary
            # but would need to change how output is printed
            predecessor_job_name = successor_job["predecessors"][predecessor_idx]
            predecessor_job = [
                jobs[i]
                for i in range(len(jobs))
                if jobs[i]["name"] == predecessor_job_name
            ][0]

            # Precedence of jobs running at different periods can be hard to reason about.
            # The following rationale for time lags and slack times is used here, where we do not discuss the different periods between the predecessor and successor, but rather focus on if for all successor job instances of any predecessor job instance satisfy the constraint. If so, then the precedence relationship is respected.
            # Time Lag: The time lag precedence relationship means that a successor job can only start a certain time lag after the predecessor job has completed. In the periodic case, for all successor job instances, if any instance of the predecessor job has completed before the time lag but after a previous successor job instance, then the precedence relationship has been met. This logic can be simplified to only check the immediate predecessor. Note the additional clause to check only the immediate predecessor job instance and not any before. This ensures that we are not checking the first predecessor job instance, which would trivially satisfy the constraint for all successor job instances thereafter. Also note the following, resulting from the logic above. A job with a smaller period cannot be a successor to a job with a higher period.
            # Slack Time: While it may be harder to comprehend, the slack time constraint is simpler to implement. The slack time precedence relationship means that a successor job must start within the slack time after the predecessor job has finished. In the periodic case, for all successor job instances, if any predecessor job instance is within the slack time and occurs before the successor job instance, then the slack time precedence relationship has been met.

            # Ensure the time lags are respected
            for successor_instance_idx in range(successor_job["instances"]):
                # Create list to hold whether a predecessor instance satisfies the time lag constraint for a successor instance
                predecessor_lag_satisfied = []

                for predecessor_instance_idx in range(predecessor_job["instances"]):
                    # Boolean variable to keep track if a particular predecessor job instance satisfies the time lag constraint for a successor job instance
                    lag_satisfied = model.new_bool_var(
                        f"successor_job_{successor_idx}_instance_{successor_instance_idx}_predecessor_job_{predecessor_idx}_instance_{predecessor_instance_idx}_time_lag"
                    )
                    predecessor_lag_satisfied.append(lag_satisfied)

                    # Reify the time lag constraint
                    # 1st condition: Ensure the predecessor instance occurs before the successor instance
                    model.add(
                        predecessor_job["start_time_var"]
                        + predecessor_instance_idx * predecessor_job["period"]
                        + predecessor_job["processing_time"]
                        <= successor_job["start_time_var"]
                        + successor_instance_idx * successor_job["period"]
                    ).only_enforce_if(lag_satisfied)
                    # 2st condition: Ensure the successor instance occurs before the next predecessor instance in the successor instance's period
                    model.add(
                        successor_job["start_time_var"]
                        >= predecessor_job["start_time_var"]
                        + predecessor_job["processing_time"]
                        + successor_job["time_lags"][predecessor_idx]
                    ).only_enforce_if(lag_satisfied)

                # Ensure that at least one predecessor instance satisfies the time lag constraint
                # As this statement is in a successor instance for loop, We add this constraint for every successor instance
                model.add_bool_or(predecessor_lag_satisfied)

            # Ensure the slack times are respected
            if successor_job["slack_times"][predecessor_idx] is not None:
                for successor_instance_idx in range(successor_job["instances"]):
                    # Create list to hold whether a predecessor instance satisfies the slack time constraint for a successor instance
                    predecessor_slack_satisfied = []

                    for predecessor_instance_idx in range(predecessor_job["instances"]):
                        # Boolean variable to keep track if a particular predecessor job instance satisfies the slack time constraint for a successor job instance
                        slack_satisfied = model.new_bool_var(
                            f"successor_job_{successor_idx}_instance_{successor_instance_idx}_predecessor_job_{predecessor_idx}_instance_{predecessor_instance_idx}_slack_time"
                        )
                        predecessor_slack_satisfied.append(slack_satisfied)

                        # For a positive slack time find any previous predecessor instance for which the slack time constraint holds
                        if successor_job["slack_times"][predecessor_idx] >= 0:
                            # Reify the slack time constraint
                            # 1st condition: Ensure the predecessor instance occurs before the successor instance
                            model.add(
                                predecessor_job["start_time_var"]
                                + predecessor_instance_idx * predecessor_job["period"]
                                + predecessor_job["processing_time"]
                                <= successor_job["start_time_var"]
                                + successor_instance_idx * successor_job["period"]
                            ).only_enforce_if(slack_satisfied)
                            # 2nd condition: Ensure the successor instance occurs within the slack of the predecessor instance
                            model.add(
                                successor_job["start_time_var"]
                                + successor_instance_idx * successor_job["period"]
                                <= predecessor_job["start_time_var"]
                                + predecessor_instance_idx * predecessor_job["period"]
                                + predecessor_job["processing_time"]
                                + successor_job["slack_times"][predecessor_idx]
                            ).only_enforce_if(slack_satisfied)

                        # For a negative slack time choose the predecessor instance that is immediately after the successor instance
                        else:
                            # TODO
                            pass

                    # Every successor instance needs to have at least one predecessor instance for which the slack time constraint is satisfied by
                    model.add_bool_or(predecessor_slack_satisfied)

# Define intermediary variables for the objective function
for idx in range(len(jobs)):
    jobs[idx]["completion_time_var"] = (
        jobs[idx]["start_time_var"] + jobs[idx]["processing_time"]
    )
    jobs[idx]["flow_time_var"] = (
        jobs[idx]["completion_time_var"] - jobs[idx]["release_time"]
        if jobs[idx]["release_time"] is not None
        else None
    )
    jobs[idx]["earliness_var"] = (
        jobs[idx]["deadline"] - jobs[idx]["completion_time_var"]
        if jobs[idx]["deadline"] is not None
        else None
    )

model.minimize(
    # Minimize the completion time
    sum(
        jobs[idx]["completion_time_weight"] * jobs[idx]["completion_time_var"]
        for idx in range(len(jobs))
    )
    +
    # Minimize the flow time
    sum(
        jobs[idx]["flow_time_weight"] * jobs[idx]["flow_time_var"]
        for idx in range(len(jobs))
        if jobs[idx]["flow_time_var"] is not None
    )
    +
    # Minimize the earliness
    sum(
        jobs[idx]["earliness_weight"] * jobs[idx]["earliness_var"]
        for idx in range(len(jobs))
        if jobs[idx]["earliness_var"] is not None
    )
)

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 60
solver.Solve(model)
status_name = solver.status_name()

# Retrieve solution
if status_name == "OPTIMAL" or status_name == "FEASIBLE":
    if all([job["start_time"] is not None for job in jobs]):
        print("Input schedule is feasible.", file=sys.stderr)
    else:
        for idx in range(len(jobs)):
            job = jobs[idx]
            job["start_time"] = solver.value(job["start_time_var"])
            job["completion_time"] = solver.value(job["completion_time_var"])
            job["flow_time"] = (
                solver.value(job["flow_time_var"])
                if job["flow_time_var"] is not None
                else None
            )
            job["earliness"] = (
                solver.value(job["earliness_var"])
                if job["earliness_var"] is not None
                else None
            )
            # Get rid of variables in our job dictionary before output
            job.pop("start_time_var", None)
            job.pop("interval_vars", None)
            job.pop("completion_time_var", None)
            job.pop("flow_time_var", None)
            job.pop("earliness_var", None)

        # Output solution formatted as csv
        writer = csv.DictWriter(sys.stdout, fieldnames=jobs[0].keys())
        writer.writeheader()
        writer.writerows(jobs)

        print("Feasible schedule found.", file=sys.stderr)

elif status_name == "INFEASIBLE":
    print("Input is not feasible!", file=sys.stderr)
elif status_name == "UNKNOWN":
    print("Solver timed out", file=sys.stderr)
else:
    print("Help ?!", file=sys.stderr)
