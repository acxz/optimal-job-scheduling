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
job_file = sys.stdin if args.input == "-" else open(args.input)
reader = csv.DictReader(job_file)

# TODO: use toml instead of csv, will ensure we can have both machines and job characteristics in one file
# machine_file = ["machine_name,speed,setup_time", "machine,,"]
machine_file = ["machine_name,speed,setup_time", "m1,,", "m2,,1"]
machine_reader = csv.DictReader(machine_file)

machines = {}
has_speed = "speed" in machine_reader.fieldnames
has_setup_time = "setup_time" in machine_reader.fieldnames

for row in machine_reader:
    machines[row["machine_name"]] = {
        "machine_name": row["machine_name"],
        "speed": int(row["speed"]) if has_speed and row["speed"] != "" else 1,
        "setup_time": int(row["setup_time"])
        if has_setup_time and row["setup_time"] != ""
        else 0,
        # Variable to check for overlap
        "interval_vars": [],
    }

jobs = {}

has_period = "period" in reader.fieldnames
has_start_time = "start_time" in reader.fieldnames
has_machine_name = "machine_name" in reader.fieldnames
has_processing_times = "processing_times" in reader.fieldnames
has_release_time = "release_time" in reader.fieldnames
has_deadline = "deadline" in reader.fieldnames
has_time_lags = "time_lags" in reader.fieldnames
has_slack_times = "slack_times" in reader.fieldnames
has_completion_time_weight = "completion_time_weight" in reader.fieldnames
has_flow_time_weight = "flow_time_weight" in reader.fieldnames
has_earliness_weight = "earliness_weight" in reader.fieldnames

for row in reader:
    # Single Machine Scheduling (1): Single processing time is provided for all jobs, with no input machine csv
    # Identical Machine Scheduling (P): Single processing time is provided for all jobs, with an input machine csv
    # Uniform Machine Scheduling (Q): Single processing time is provided for all jobs, with an input machine csv specifying speed
    # Unrelated Machine Scheduling (R): Multiple processing times provided for all jobs, with an input machine csv

    # Create processing times based on input processing times and machine input
    processing_times = (
        ast.literal_eval(row["processing_times"])
        if has_processing_times and row["processing_times"] != ""
        else 1
    )
    # If input processing times is integer, apply that processing time to all machines
    if isinstance(processing_times, int):
        processing_time = processing_times
        processing_times = {
            machine_name: processing_time for machine_name in machines.keys()
        }

    jobs[row["job_name"]] = {
        "job_name": row["job_name"],
        # At least one period must be specified
        "period": int(row["period"]) if has_period and row["period"] != "" else None,
        "start_time": int(row["start_time"])
        if has_start_time and row["start_time"] != ""
        else None,
        "machine_name": row["machine_name"]
        if has_machine_name and row["machine_name"] != ""
        else None,
        "processing_times": processing_times,
        "release_time": int(row["release_time"])
        if has_release_time and row["release_time"] != ""
        else None,
        "deadline": int(row["deadline"])
        if has_deadline and row["deadline"] != ""
        else None,
        "time_lags": ast.literal_eval(row["time_lags"])
        if has_time_lags and row["time_lags"] != ""
        else None,
        "slack_times": ast.literal_eval(row["slack_times"])
        if has_slack_times and row["slack_times"] != ""
        else None,
        "completion_time_weight": int(row["completion_time_weight"])
        if has_completion_time_weight and row["completion_time_weight"] != ""
        else 0,
        "flow_time_weight": int(row["flow_time_weight"])
        if has_flow_time_weight and row["flow_time_weight"] != ""
        else 0,
        "earliness_weight": int(row["earliness_weight"])
        if has_earliness_weight and row["earliness_weight"] != ""
        else 0,
        # variables to solve for
        "start_time_var": None,
        "machine_name_var": None,
        "processing_time_var": None,
        "interval_vars": [],
    }

# Flag to exit after checking input
input_error = False

# Ensure that a job can run on the machine specified
for job_name, job in jobs.items():
    if job["machine_name"] is not None:
        # If the machine is specified, make sure the machine exists
        if job["machine_name"] not in machines.keys():
            print(
                f"Job {job_name} is specified to run on machine {job['machine_name']} but that machine is not specified!",
                file=sys.stderr,
            )
            input_error = True

        # If the machine is specified, key off the machine in the processing times
        if job["machine_name"] not in job["processing_times"].keys():
            print(
                f"Job {job_name} is specified to run on machine {job['machine_name']} for which a processing time is not specified!",
                file=sys.stderr,
            )
            input_error = True
    # If the machine is not specified and there is only one machine/processing time pair specified, then job must run on that machine if machine exists
    else:
        if len(job["processing_times"]) == 1:
            processing_machine_name = list(job["processing_times"].keys())[0]
            if processing_machine_name in machines.keys():
                job["machine_name"] = processing_machine_name
            else:
                print(
                    f"Job {job_name} is specified to run on machine {processing_machine_name} but that machine is not specified!",
                    file=sys.stderr,
                )
                input_error = True

# Ensure that each predecessor in time lags and slack times has been specified
for job_name, job in jobs.items():
    if job["time_lags"] is not None:
        for predecessor_job_name in job["time_lags"].keys():
            if predecessor_job_name not in jobs.keys():
                print(
                    f"Job {job_name} has a time lag predecessor, {predecessor_job_name}, that does not exist!",
                    file=sys.stderr,
                )
                input_error = True
    if job["slack_times"] is not None:
        for predecessor_job_name in job["slack_times"].keys():
            if predecessor_job_name not in jobs.keys():
                print(
                    f"Job {job_name} has a slack time predecessor, {predecessor_job_name}, that does not exist!",
                    file=sys.stderr,
                )
                input_error = True

# Ensure that at least one job has its period specified
if all([job["period"] is None for job in jobs.values()]):
    print(
        f"At least one job must have its period specified!",
        file=sys.stderr,
    )
    input_error = True

if input_error:
    sys.exit()

# Compute the hyper-period of the schedule
periods = [job["period"] for job in jobs.values() if job["period"] is not None]
hyper_period = math.lcm(*periods)

# Assign the period of non-periodic jobs as the hyper-period
for job in jobs.values():
    if job["period"] is None:
        job["period"] = hyper_period

# Obtain the number of instances for each job in the hyper-period
for job in jobs.values():
    job["instances"] = hyper_period // job["period"]

model = cp_model.CpModel()

for job_name, job in jobs.items():
    # Determine the processing time of a job based on the machine it is run on
    if job["machine_name"] is None:
        # TODO: need to reify based on machine id, index constraint?
        sys.exit("Auto-Scheduling on multiple machines not supported yet!")
    else:
        # TODO: this will need to be a reified variable to determine processing time based on machine
        job["processing_time_var"] = job["processing_times"][job["machine_name"]]
        # TODO: this will need to be an index variable to schedule jobs on multiple machines
        job["machine_name_var"] = job["machine_name"]

    # Ensure the job starts within its period
    if job["start_time"] is None:
        job["start_time_var"] = model.new_int_var(
            0,
            job["period"],
            f"{job_name}_start_time",
        )
    # If the start time is specified then ensure the start time is respected
    else:
        job["start_time_var"] = model.new_constant(job["start_time"])

    # TODO: Jobs wrapping around its period is not yet supported
    # Would need to reify on the below condition, and create two intervals to check no_overlap
    model.add(job["start_time_var"] <= job["period"] - job["processing_time_var"])

    # Ensure the release time and deadline are respected
    # In this context of periodicity, release time and deadline are defined as
    # a time within the job's first period
    if job["release_time"] is not None:
        model.add(job["start_time_var"] >= job["release_time"])

    if job["deadline"] is not None:
        model.add(job["start_time_var"] + job["processing_time_var"] <= job["deadline"])

    for instance_idx in range(job["instances"]):
        # An interval variable for each instance of the job during the cycle is
        # created to ensure no interval overlap
        job_instance_interval_var = model.new_fixed_size_interval_var(
            job["start_time_var"] + instance_idx * job["period"],
            job["processing_time_var"],
            f"{job_name}_instance_{instance_idx}_interval",
        )
        job["interval_vars"].append(job_instance_interval_var)

    # Add job interval vars to its assigned machine's interval vars
    # TODO: Reify on machine_name_var for machine scheduling
    machines[job["machine_name_var"]]["interval_vars"] = (
        machines[job["machine_name_var"]]["interval_vars"] + job["interval_vars"]
    )

# Add no overlap for intervals on the same machine
for machine_name, machine in machines.items():
    model.add_no_overlap(machine["interval_vars"])

# Precedence of jobs running at different periods can be hard to reason about.
# The following rationale for time lags and slack times is used here, where we do not discuss the different periods between the predecessor and successor, but rather focus on if for all successor job instances of any predecessor job instance satisfy the constraint. If so, then the precedence relationship is respected.
# Time Lag: The time lag precedence relationship means that a successor job can only start a certain time lag after the predecessor job has completed. In the periodic case, for all successor job instances, if any instance of the predecessor job has completed before the time lag but after a previous successor job instance, then the precedence relationship has been met. This logic can be simplified to only check the immediate predecessor. Note the additional clause to check only the immediate     predecessor job instance and not any before. This ensures that we are not checking the first predecessor job instance, which would trivially satisfy the constraint for all successor job instances thereafter. Also note the following, resulting from the logic above. A job with a smaller period cannot be a successor to a job with a higher period.
# Slack Time: While it may be harder to comprehend, the slack time constraint is simpler to implement. The slack time precedence relationship means that a successor job must start within the slack time after the predecessor job has finished. In the periodic case, for all successor job instances, if any predecessor job instance is within the slack time and occurs before the successor job instance, then the slack time precedence relationship has been met.

# To add precedence constraints run a second pass through the jobs
# to ensure all the jobs' start time and processing time variables have been created
for successor_job_name, successor_job in jobs.items():
    # Ensure the time lags are respected
    if successor_job["time_lags"] is not None:
        for predecessor_job_name, successor_time_lag in successor_job[
            "time_lags"
        ].items():
            # Get the predecessor job
            predecessor_job = jobs[predecessor_job_name]

            for successor_instance_idx in range(successor_job["instances"]):
                # Create list to hold whether a predecessor instance satisfies the time lag constraint for a successor instance
                predecessor_lag_satisfied = []

                for predecessor_instance_idx in range(predecessor_job["instances"]):
                    # Boolean variable to keep track if a particular predecessor job instance satisfies the time lag constraint for a successor job instance
                    lag_satisfied = model.new_bool_var(
                        f"successor_{successor_job_name}_instance_{successor_instance_idx}_predecessor_{predecessor_job_name}_instance_{predecessor_instance_idx}_time_lag"
                    )
                    predecessor_lag_satisfied.append(lag_satisfied)

                    # Reify the time lag constraint
                    # 1st condition: Ensure the predecessor instance occurs before the successor instance
                    model.add(
                        predecessor_job["start_time_var"]
                        + predecessor_instance_idx * predecessor_job["period"]
                        + predecessor_job["processing_time_var"]
                        <= successor_job["start_time_var"]
                        + successor_instance_idx * successor_job["period"]
                    ).only_enforce_if(lag_satisfied)
                    # 2st condition: Ensure the successor instance occurs before the next predecessor instance in the successor instance's period
                    model.add(
                        successor_job["start_time_var"]
                        >= predecessor_job["start_time_var"]
                        + predecessor_job["processing_time_var"]
                        + successor_time_lag
                    ).only_enforce_if(lag_satisfied)

                # Ensure that at least one predecessor instance satisfies the time lag constraint
                # As this statement is in a successor instance for loop, We add this constraint for every successor instance
                model.add_bool_or(predecessor_lag_satisfied)

    # Ensure the slack times are respected
    if successor_job["slack_times"] is not None:
        for predecessor_job_name, successor_slack_time in successor_job[
            "slack_times"
        ].items():
            # Get the predecessor job
            predecessor_job = jobs[predecessor_job_name]

            for successor_instance_idx in range(successor_job["instances"]):
                # Create list to hold whether a predecessor instance satisfies the slack time constraint for a successor instance
                predecessor_slack_satisfied = []

                for predecessor_instance_idx in range(predecessor_job["instances"]):
                    # Boolean variable to keep track if a particular predecessor job instance satisfies the slack time constraint for a successor job instance
                    slack_satisfied = model.new_bool_var(
                        f"successor_{successor_job_name}_instance_{successor_instance_idx}_predecessor_{predecessor_job_name}_instance_{predecessor_instance_idx}_slack_time"
                    )
                    predecessor_slack_satisfied.append(slack_satisfied)

                    # For a positive slack time find any previous predecessor instance for which the slack time constraint holds
                    if successor_slack_time >= 0:
                        # Reify the slack time constraint
                        # 1st condition: Ensure the predecessor instance occurs before the successor instance
                        model.add(
                            predecessor_job["start_time_var"]
                            + predecessor_instance_idx * predecessor_job["period"]
                            + predecessor_job["processing_time_var"]
                            <= successor_job["start_time_var"]
                            + successor_instance_idx * successor_job["period"]
                        ).only_enforce_if(slack_satisfied)
                        # 2nd condition: Ensure the successor instance occurs within the slack of the predecessor instance
                        model.add(
                            successor_job["start_time_var"]
                            + successor_instance_idx * successor_job["period"]
                            <= predecessor_job["start_time_var"]
                            + predecessor_instance_idx * predecessor_job["period"]
                            + predecessor_job["processing_time_var"]
                            + successor_slack_time
                        ).only_enforce_if(slack_satisfied)

                    # For a negative slack time choose the predecessor instance that is immediately after the successor instance
                    else:
                        # TODO
                        pass

                # Every successor instance needs to have at least one predecessor instance for which the slack time constraint is satisfied by
                model.add_bool_or(predecessor_slack_satisfied)

# Define intermediary variables for the objective function
for job in jobs.values():
    job["completion_time_var"] = job["start_time_var"] + job["processing_time_var"]
    job["flow_time_var"] = (
        job["completion_time_var"] - job["release_time"]
        if job["release_time"] is not None
        else None
    )
    job["earliness_var"] = (
        job["deadline"] - job["completion_time_var"]
        if job["deadline"] is not None
        else None
    )

model.minimize(
    # Minimize the completion time
    sum(
        job["completion_time_weight"] * job["completion_time_var"]
        for job in jobs.values()
    )
    +
    # Minimize the flow time
    sum(
        job["flow_time_weight"] * job["flow_time_var"]
        for job in jobs.values()
        if job["flow_time_var"] is not None
    )
    +
    # Minimize the earliness
    sum(
        job["earliness_weight"] * job["earliness_var"]
        for job in jobs.values()
        if job["earliness_var"] is not None
    )
)

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 60
solver.Solve(model)
status_name = solver.status_name()

# Retrieve solution
if status_name == "OPTIMAL" or status_name == "FEASIBLE":
    # If start times and machine names specified for all jobs, then the input was feasible
    if all(
        [
            job["start_time"] is not None and job["machine_name"] is not None
            for job in jobs.values()
        ]
    ):
        print("Input schedule is feasible.", file=sys.stderr)
    else:
        print("Feasible schedule found.", file=sys.stderr)

    for job in jobs.values():
        job["start_time"] = solver.value(job["start_time_var"])
        job["machine_name"] = job["machine_name_var"]
        job["processing_time"] = solver.value(job["processing_time_var"])
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
        job.pop("machine_name_var", None)
        job.pop("processing_time_var", None)
        job.pop("interval_vars", None)
        job.pop("completion_time_var", None)
        job.pop("flow_time_var", None)
        job.pop("earliness_var", None)

    # Output solution formatted as csv
    job_characteristics = list(jobs.values())[0].keys()
    writer = csv.DictWriter(sys.stdout, fieldnames=job_characteristics)
    writer.writeheader()
    writer.writerows(jobs.values())

elif status_name == "INFEASIBLE":
    print("Input is not feasible!", file=sys.stderr)
elif status_name == "UNKNOWN":
    print("Solver timed out", file=sys.stderr)
else:
    print("Model Invalid", file=sys.stderr)
