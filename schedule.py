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
import tomllib

parser = argparse.ArgumentParser()
parser.add_argument(
    "input",
    type=str,
    nargs="?",
    default="-",  # use "-" to denote stdin by convention
    help="toml of machines and jobs specifying their characteristics. If all start times and machines are specified, then the start times and machines are checked for.",
)

# TODO: Describe input in detail for each field in help
# i.e. possible values, default values, and what if left blank
# Single Machine Scheduling (1): Single processing time is provided for all jobs, with no input machine csv
# Identical Machine Scheduling (P): Single processing time is provided for all jobs, with an input machine csv
# Uniform Machine Scheduling (Q): Single processing time is provided for all jobs, with an input machine csv specifying speed
# Unrelated Machine Scheduling (R): Multiple processing times provided for all jobs, with an input machine csv

args = parser.parse_args()
schedule_input_file = sys.stdin.buffer if args.input == "-" else open(args.input, "rb")
if args.input == "-" and sys.stdin.isatty():
    print(
        "To signal the end of manual input, make sure to enter `Ctrl-D` on Unix systems and `Ctrl-Z` on Windows.\nWaiting for user input...",
        file=sys.stderr,
    )
schedule_input = tomllib.load(schedule_input_file)

# Populate periodic key if not specified
if "periodic" not in schedule_input.keys():
    schedule_input["periodic"] = True

# Populate machines with a single machine if not specified
if "machines" not in schedule_input.keys():
    schedule_input["machines"] = {"machine": {}}

# Check that at least one job is specified
if "jobs" not in schedule_input.keys() or len(schedule_input["jobs"]) == 0:
    print(
        f"No jobs specified!",
        file=sys.stderr,
    )
    sys.exit()

# Parse in periodic, machines, and jobs from schedule input
is_schedule_periodic = schedule_input["periodic"]
machines = schedule_input["machines"]
jobs = schedule_input["jobs"]

# Set default values and variables to solve for machines
for machine in machines.values():
    if "speed" not in machine.keys():
        machine["speed"] = 1
    if "setup_time" not in machine.keys():
        machine["setup_time"] = 0
    if "teardown_time" not in machine.keys():
        machine["teardown_time"] = 0
    # Variable to check for job overlap
    machine["interval_vars"] = []

for job in jobs.values():
    # Create processing times based on input processing times and machine input
    if "processing_times" not in job.keys():
        job["processing_times"] = 1
    # If input processing times is integer, apply that processing time to all machines
    if isinstance(job["processing_times"], int):
        processing_time = job["processing_times"]
        job["processing_times"] = {
            machine_name: processing_time for machine_name in machines.keys()
        }

    if "period" not in job.keys():
        job["period"] = None
    if "start_time" not in job.keys():
        job["start_time"] = None
    if "completion_time" not in job.keys():
        job["completion_time"] = None
    if "machine" not in job.keys():
        job["machine"] = None
    if "same_machine_jobs" not in job.keys():
        job["same_machine_jobs"] = []
    if "different_machine_jobs" not in job.keys():
        job["different_machine_jobs"] = []
    if "release_time" not in job.keys():
        job["release_time"] = None
    if "deadline" not in job.keys():
        job["deadline"] = None
    if "completion_time_weight" not in job.keys():
        job["completion_time_weight"] = 0
    if "flow_time_weight" not in job.keys():
        job["flow_time_weight"] = 0
    if "earliness_weight" not in job.keys():
        job["earliness_weight"] = 0

    if "predecessors" not in job.keys():
        job["predecessors"] = {}
    for pred_job_name, pred_characteristics in job["predecessors"].items():
        if "start_time_wrt" not in pred_characteristics.keys():
            pred_characteristics["start_time_wrt"] = None
        if "completion_time_wrt" not in pred_characteristics.keys():
            pred_characteristics["completion_time_wrt"] = None
        if "time_lag" not in pred_characteristics.keys():
            pred_characteristics["time_lag"] = None
        if "slack_time" not in pred_characteristics.keys():
            pred_characteristics["slack_time"] = None
        if "flow_time_wrt_weight" not in pred_characteristics.keys():
            pred_characteristics["flow_time_wrt_weight"] = 0
        if "earliness_wrt_weight" not in pred_characteristics.keys():
            pred_characteristics["earliness_wrt_weight"] = 0

    # Variables to solve for
    job |= {
        "start_time_var": None,
        "machine_vars": [],
        "machine_var": None,
        "processing_time_var": None,
        "start+processing_time_var": None,
        "completion_time_var": None,
    }

# Flag to exit after checking input
input_error = False

# Ensure that a job can run on the machine specified
for job_name, job in jobs.items():
    if job["machine"] is not None:
        # If the machine is specified, make sure the machine exists
        if job["machine"] not in machines.keys():
            print(
                f"Job {job_name} is specified to run on machine {job['machine']} but that machine is not specified!",
                file=sys.stderr,
            )
            input_error = True

        # If the machine is specified, key off the machine in the processing times
        if job["machine"] not in job["processing_times"].keys():
            print(
                f"Job {job_name} is specified to run on machine {job['machine']} for which a processing time is not specified!",
                file=sys.stderr,
            )
            input_error = True
    # If the machine is not specified
    else:
        # If there is only one machine and if there is a processing time associated with it, then job must run on that machine
        if len(machines) == 1:
            machine_name = list(machines.keys())[0]
            if machine_name in job["processing_times"].keys():
                job["machine"] = machine_name
            else:
                print(
                    f"Job {job_name} is not specified to run on the sole machine {machine_name}!",
                    file=sys.stderr,
                )
                input_error = True
        # If there is only one machine/processing time pair specified, then job must run on that machine if machine exists
        if len(job["processing_times"]) == 1:
            processing_machine = list(job["processing_times"].keys())[0]
            if processing_machine in machines.keys():
                job["machine"] = processing_machine
            else:
                print(
                    f"Job {job_name} is specified to run on machine {processing_machine} but that machine is not specified!",
                    file=sys.stderr,
                )
                input_error = True

# Ensure that predecessors have been specified
for job_name, job in jobs.items():
    for predecessor_job_name in job["predecessors"].keys():
        if predecessor_job_name not in jobs.keys():
            print(
                f"Job {job_name} has predecessor, {predecessor_job_name}, that does not exist!",
                file=sys.stderr,
            )
            input_error = True

# Ensure that at least one job has its period specified
if all([job["period"] is None for job in jobs.values()]):
    print(
        f"At least one job must have its period specified! For non-periodic scheduling simply, treat the period as the max time for your schedule.",
        file=sys.stderr,
    )
    input_error = True

# Compute the hyper-period of the schedule
periods = [job["period"] for job in jobs.values() if job["period"] is not None]
hyper_period = math.lcm(*periods)

# Assign the period of jobs that have none as the hyper-period
# and obtain the number of instances for each job in the hyper-period
for job in jobs.values():
    if job["period"] is None:
        job["period"] = hyper_period
    job["instances"] = hyper_period // job["period"]

# Ensure that all jobs have the same period (aka max time) if periodic is false
first_job_period = list(jobs.values())[0]["period"]
if not is_schedule_periodic:
    if not all([job["period"] == first_job_period for job in jobs.values()]):
        print(
            f"For non-periodic schedules, the periods of each job, if specified, must be the same! At least one period must be specified, you can treat this as the max time for your schedule.",
            file=sys.stderr,
        )
        input_error = True

if input_error:
    sys.exit()

# For periodic schedules ensure we check with intervals before the 1st period
# This allows us to check for interval overlaps with jobs starting in the previous period, but wrapping around to the current period
interval_instance_start_idx = -1 if is_schedule_periodic else 0

# For periodic schedules ensure we check with predecessors before the 1st period
# This allows us to check for precedence relations with the previous period
predecessor_instance_start_idx = -1 if is_schedule_periodic else 0

model = cp_model.CpModel()

for job_name, job in jobs.items():
    # Ensure the job starts within its period
    if job["start_time"] is None:
        job["start_time_var"] = model.new_int_var(
            0,
            job["period"] - 1,
            f"job_{job_name}_start_time",
        )
    # If the start time is specified then ensure the start time is respected
    # Handle values outside of the first period via module with the job's period
    else:
        job["start_time_var"] = model.new_constant(job["start_time"] % job["period"])

    # Define the completion time variable that handles a job wrapping around its period with a modulo equality
    if job["completion_time"] is None:
        job["completion_time_var"] = model.new_int_var(
            1, job["period"], f"job_{job_name}_completion_time"
        )
    # If the completion time is specified then ensure the completion time is respected
    # Handle values outside of the first period via module with the job's period
    # Since completion time is defined as [1, job's period] modify the modulo output
    # to give job's period when the result would be 0 (outside of the range)
    else:
        job["completion_time_var"] = model.new_constant(
            job["completion_time"] % job["period"]
            if job["completion_time"] % job["period"] != 0
            else job["period"]
        )

    # Ensure the release time and deadline are respected
    # Release time and deadline are defined as a time within the job's period
    # Handle values outside of the first period via module with the job's period
    if job["release_time"] is not None:
        model.add(job["start_time_var"] >= job["release_time"] % job["period"])

    if job["deadline"] is not None:
        # Note that we use job["completion_time_var"] and not job["start+processing_time_var"]
        # since the deadline is defined within the period
        # Since completion time is defined as [1, job's period] modify the modulo output
        # to give job's period when the result would be 0 (outside of the range)
        model.add(
            job["completion_time_var"] <= job["deadline"] % job["period"]
            if job["deadline"] % job["period"] != 0
            else job["period"]
        )

    # Constraints on assigning the job to a machine
    # Option 1: Boolean approach
    # Boolean variable to determine if job is run on that machine
    job["machine_vars"] = [
        model.new_bool_var(f"job_{job_name}_assigned_on_machine_{machine_name}")
        for machine_name in machines.keys()
    ]

    # Ensure the job runs only on one machine
    model.add_exactly_one(job["machine_vars"])

    # If the machine is specified then ensure the job runs on that machine
    if job["machine"] is not None:
        # Determine the index of the machine to recover the boolean variable that specifies if the job is assigned to this machine
        machine_idx = list(machines.keys()).index(job["machine"])
        job_assigned_on_machine_var = job["machine_vars"][machine_idx]

        # Ensure that the job is assigned on the machine
        model.add(job_assigned_on_machine_var == True)

    # If job has no processing time for a machine, ensure the job cannot be assigned to that machine
    for machine_name in machines.keys():
        if not machine_name in job["processing_times"]:
            machine_idx = list(machines.keys()).index(machine_name)
            job_assigned_on_machine_var = job["machine_vars"][machine_idx]
            model.add(job_assigned_on_machine_var == False)

    # Option 2: Element approach
    # Create a variable for the machine index that corresponds to the machine the job runs on
    job["machine_var"] = model.new_int_var(
        0, len(machines) - 1, f"job_{job_name}_assigned_on_machine"
    )

    # If the machine is specified then ensure the job runs on that machine
    if job["machine"] is not None:
        # Determine the index of the machine in the machines dictionary
        machine_idx = list(machines.keys()).index(job["machine"])

        # Ensure that the job is assigned on the machine
        model.add(job["machine_var"] == machine_idx)

    # If job has no processing time for a machine, ensure the job cannot be assigned to that machine
    for machine_name in machines.keys():
        if not machine_name in job["processing_times"]:
            machine_idx = list(machines.keys()).index(machine_name)
            model.add(job["machine_var"] != machine_idx)

    # TODO: determine how to use a variable mapping
    # Recover the machine assigned to this job
    # Determine the index of the machine in the machines dictionary
    machine_idx = list(machines.keys()).index(job["machine"])
    machine_name = list(machines.keys())[machine_idx]
    machine = machines[machine_name]

    # Create a domain variable for processing time with possible processing times for the job
    processing_time_domain = cp_model.Domain.from_values(
        list(job["processing_times"].values())
    )
    job["processing_time_var"] = model.new_int_var_from_domain(
        processing_time_domain, f"job_{job_name}_processing_time"
    )

    # Determine the processing time of a job based on the machine it is run on
    # FIXME: Override as constant until machine scheduling implemented
    job["processing_time_var"] = model.new_constant(
        job["processing_times"][machine_name]
    )

    # Create a variable to represent the sum of start time and processing time to use in future constraints
    # Note: It is important to understand when to use job["start_time_var"] + job["processing_time_var"] vs job["completion_time_var"]
    # as both represent the completion time, but the first represents the completion time of the job that has started in the current period,
    # while the second one represents the completion time of the job that started in the previous period
    # The upper bound is 2 times the job's period minus 1 as remember this variable can overrun the current period.
    # However if it overruns 2 periods, then the job will overlap with another instance of itself.
    job["start+processing_time_var"] = model.new_int_var(
        0, 2 * job["period"] - 1, f"job_{job_name}_start+processing_time"
    )
    model.add(
        job["start+processing_time_var"]
        == job["start_time_var"] + job["processing_time_var"]
    )

    # Ensure the completion time is equal to start time plus processing time, while accounting for wrapping around the start of its period
    model.add_modulo_equality(
        job["completion_time_var"],
        job["start+processing_time_var"],
        job["period"],
    )

    # Create a job interval for every instance in the period accounting for setup time and teardown time
    for instance_idx in range(interval_instance_start_idx, job["instances"]):
        machine_job_instance_interval_var = model.new_interval_var(
            job["start_time_var"]
            + instance_idx * job["period"]
            - machine["setup_time"],
            machine["setup_time"]
            + job["processing_time_var"]
            + machine["teardown_time"],
            job["start+processing_time_var"]
            + instance_idx * job["period"]
            + machine["teardown_time"],
            f"machine_{machine_name}_job_{job_name}_instance_{instance_idx}_interval",
        )

        # Add job instance interval var to its assigned machine's interval vars
        machines[machine_name]["interval_vars"].append(
            machine_job_instance_interval_var
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
# If a job specifies a time lag and a slack time for the same predecessor job,
# an additional constraint is added that ensures the time lag and slack time constraints are both applied on the same predecessor instance
for successor_job_name, successor_job in jobs.items():
    for predecessor_job_name, pred_characteristics in successor_job[
        "predecessors"
    ].items():
        # Get the predecessor job and its characteristics
        predecessor_job = jobs[predecessor_job_name]
        time_lag = pred_characteristics.get("time_lag")
        slack_time = pred_characteristics.get("slack_time")

        # Ensure the time lag + slack time is respected with the same predecessor instance if both specified for the same predecessor
        if time_lag is not None and slack_time is not None:
            for successor_instance_idx in range(successor_job["instances"]):
                # Create list to hold whether a predecessor instance satisfies the time lag and slack time constraint for a successor instance
                predecessor_lag_slack_satisifed = []

                for predecessor_instance_idx in range(
                    predecessor_instance_start_idx, predecessor_job["instances"]
                ):
                    # Boolean variable to keep track if a particular predecessor job instance satisfies the time lag + slack time constraint for a successor job instance
                    lag_slack_satisfied = model.new_bool_var(
                        f"successor_{successor_job_name}_instance_{successor_instance_idx}_predecessor_{predecessor_job_name}_instance_{predecessor_instance_idx}_time_lag_slack_time"
                    )
                    predecessor_lag_slack_satisifed.append(lag_slack_satisfied)
                    # Reify the time lag + slack time constraint
                    # 1st condition: Ensure the predecessor instance occurs before the successor instance
                    model.add(
                        predecessor_job["completion_time_var"]
                        + predecessor_instance_idx * predecessor_job["period"]
                        + time_lag
                        <= successor_job["start_time_var"]
                        + successor_instance_idx * successor_job["period"]
                    ).only_enforce_if(lag_slack_satisfied)
                    # 2nd condition: Ensure the successor instance occurs within the slack of the predecessor instance
                    model.add(
                        predecessor_job["completion_time_var"]
                        + predecessor_instance_idx * predecessor_job["period"]
                        + slack_time
                        >= successor_job["start_time_var"]
                        + successor_instance_idx * successor_job["period"]
                    ).only_enforce_if(lag_slack_satisfied)

                # Ensure that at least one predecessor instance satisfies the time lag + slack time constraint
                model.add_bool_or(predecessor_lag_slack_satisifed)

        # Ensure the time lags are respected
        if time_lag is not None:
            for successor_instance_idx in range(successor_job["instances"]):
                # Create list to hold whether a predecessor instance satisfies the time lag constraint for a successor instance
                predecessor_lag_satisfied = []

                for predecessor_instance_idx in range(
                    predecessor_instance_start_idx, predecessor_job["instances"]
                ):
                    # Boolean variable to keep track if a particular predecessor job instance satisfies the time lag constraint for a successor job instance
                    lag_satisfied = model.new_bool_var(
                        f"successor_{successor_job_name}_instance_{successor_instance_idx}_predecessor_{predecessor_job_name}_instance_{predecessor_instance_idx}_time_lag"
                    )
                    predecessor_lag_satisfied.append(lag_satisfied)

                    # Reify the time lag constraint
                    # 1st condition: Ensure the predecessor instance occurs before the successor instance
                    model.add(
                        predecessor_job["completion_time_var"]
                        + predecessor_instance_idx * predecessor_job["period"]
                        + time_lag
                        <= successor_job["start_time_var"]
                        + successor_instance_idx * successor_job["period"]
                    ).only_enforce_if(lag_satisfied)
                    # 2nd condition: Ensure the predecessor instance occurs within one successor period
                    model.add(
                        predecessor_job["completion_time_var"]
                        + predecessor_instance_idx * predecessor_job["period"]
                        + successor_job["period"]
                        <= successor_job["start_time_var"]
                        + (successor_instance_idx + 1) * successor_job["period"]
                    ).only_enforce_if(lag_satisfied)

                # Ensure that at least one predecessor instance satisfies the time lag constraint
                # As this statement is in a successor instance for loop, We add this constraint for every successor instance
                model.add_bool_or(predecessor_lag_satisfied)

        # Ensure the slack times are respected
        if slack_time is not None:
            for successor_instance_idx in range(successor_job["instances"]):
                # Create list to hold whether a predecessor instance satisfies the slack time constraint for a successor instance
                predecessor_slack_satisfied = []

                for predecessor_instance_idx in range(
                    predecessor_instance_start_idx, predecessor_job["instances"]
                ):
                    # Boolean variable to keep track if a particular predecessor job instance satisfies the slack time constraint for a successor job instance
                    slack_satisfied = model.new_bool_var(
                        f"successor_{successor_job_name}_instance_{successor_instance_idx}_predecessor_{predecessor_job_name}_instance_{predecessor_instance_idx}_slack_time"
                    )
                    predecessor_slack_satisfied.append(slack_satisfied)

                    # Find any previous predecessor instance for which the slack time constraint holds
                    # Reify the slack time constraint
                    # 1st condition: Ensure the successor instance occurs within the slack of the predecessor instance
                    model.add(
                        predecessor_job["completion_time_var"]
                        + predecessor_instance_idx * predecessor_job["period"]
                        + slack_time
                        >= successor_job["start_time_var"]
                        + successor_instance_idx * successor_job["period"]
                    ).only_enforce_if(slack_satisfied)
                    # 2nd condition: Ensure the predecessor instance occurs within one successor period
                    model.add(
                        predecessor_job["completion_time_var"]
                        + predecessor_instance_idx * predecessor_job["period"]
                        + successor_job["period"]
                        <= successor_job["start_time_var"]
                        + (successor_instance_idx + 1) * successor_job["period"]
                    ).only_enforce_if(slack_satisfied)

                # Every successor instance needs to have at least one predecessor instance for which the slack time constraint is satisfied by
                model.add_bool_or(predecessor_slack_satisfied)

# Define intermediary variables for the objective function
for job in jobs.values():
    job["flow_time_var"] = (
        job["start+processing_time_var"] - job["release_time"]
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
    # If start times or completion times and machine names specified for all jobs, then the input was feasible
    if all(
        [
            job["start_time"] is not None
            or job["completion_time"] is not None
            and job["machine"] is not None
            for job in jobs.values()
        ]
    ):
        print("Input schedule is feasible.", file=sys.stderr)
    else:
        print("Feasible schedule found.", file=sys.stderr)

    for job_name, job in jobs.items():
        job["start_time"] = solver.value(job["start_time_var"])
        job["completion_time"] = solver.value(job["completion_time_var"])
        machine_idx = solver.value(job["machine_var"])
        job["machine"] = list(machines.keys())[machine_idx]
        job["processing_time"] = solver.value(job["processing_time_var"])
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
        job.pop("completion_time_var", None)
        job.pop("machine_vars", None)
        job.pop("machine_var", None)
        job.pop("processing_time_var", None)
        job.pop("start+processing_time_var", None)
        job.pop("flow_time_var", None)
        job.pop("earliness_var", None)

        # Prepend the job name value under the job key for readability
        jobs[job_name] = {"job": job_name} | jobs[job_name]

    # Output solution formatted as csv
    job_characteristics = list(jobs.values())[0].keys()
    writer = csv.DictWriter(sys.stdout, fieldnames=job_characteristics)
    writer.writeheader()
    writer.writerows(jobs.values())

elif status_name == "INFEASIBLE":
    print("Input is not feasible!", file=sys.stderr)
else:
    print(status_name, file=sys.stderr)
