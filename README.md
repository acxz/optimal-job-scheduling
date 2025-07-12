# $1|r_j;prec|\sum w_j C_j$ Periodic Scheduling

This repository serves to provide utilities for creating, verifying, and visualizing [periodic](https://epubs.siam.org/doi/abs/10.1137/0402049) [scheduling problems](https://en.wikipedia.org/wiki/Optimal_job_scheduling) (PSP) / periodic event scheduling problems (PESP). In particular, the scheduling problem being solved here is defined as $1|r_j;prec|\sum w_j C_j$ according to the [$\alpha|\beta|\gamma$ scheduling notation](https://en.wikipedia.org/w/index.php?title=Notation_for_theoretic_scheduling_problems) and has the following characteristics:

* single stage
* [single machine](https://en.wikipedia.org/wiki/Single-machine_scheduling)
* arbitrary processing times
* arbitrary release times
* arbitrary due dates
* precedence relations
* arbitrary time lags
* arbitrary slack times $^1$
* minimize a weighted sum of completion times
* periodic

$^1$ The slack time between two jobs is the amount of time in which the second job must be started after the first job is completed. Formally, if job $i$ precedes job $j$, then $C_i + s_{ij} \geq S_j$ must be true. $C_i$ is the completion time of job $i$, $s_{ij}$ is the slack time job $j$ is allowed following job $i$, and $S_j$ is the start time of job $j$.
The term is based on [project management terminology](https://en.wikipedia.org/wiki/Float_(project_management)) as the $\alpha|\beta|\gamma$ scheduling notation has no widespread term for this concept.

Insert image from visualize to show

## Dependencies

* [uv](https://docs.astral.sh/uv/)

## `schedule.py`

This script attempts to find a feasible schedule based on the parameters of the problem. The parameters are specified via an input csv file. If a feasible schedule exists, an output csv is created with the start times that have been solved for as well as the input parameters. This output can be visualized with the `schedule_viz.py` script. If the start times are all specified, the script verifies if the schedule is feasible.

To create or verify a schedule enter the following in the terminal:

```bash
uv run schedule.py schedule_input.csv
```

The output is sent to the [standard output (stdout)](https://en.wikipedia.org/wiki/Standard_streams#Standard_output_(stdout)). To capture the output in a file for most shells, run like so:

```bash
uv run schedule.py schedule_input.csv > schedule_output.csv
```

Note that PowerShell support for stdout is slightly broken. See [this workaround](https://github.com/PowerShell/PowerShell/issues/5974#issuecomment-1297513901).

## `schedule_viz.py`

A schedule csv file can be visualized with the `schedule_viz.py` script like so:

```bash
uv run schedule_viz.py schedule_output.csv
```

## Additional Notes

### CP-SAT

The underlying solver used for this codebase is [CP-SAT](https://developers.google.com/optimization/cp) which is a part of [OR-Tools](https://developers.google.com/optimization/). In addition to the [Scheduling Overview](https://developers.google.com/optimization/scheduling) provided in OR-Tools' documentation, [@d-krupke](https://github.com/d-krupke)'s [CP-SAT Primer](https://d-krupke.github.io/cpsat-primer/) has a wonderful section on [scheduling](https://d-krupke.github.io/cpsat-primer/04B_advanced_modelling.html#scheduling-and-packing-with-intervals). For another resource on constraint programming with CP-SAT, take a look at [Lecture 8: Intro to Constraint Programming](https://www.cis.upenn.edu/~cis1890/files/Lecture8.pdf) and [Lecture 9: More Constraint Programming](https://www.cis.upenn.edu/~cis1890/files/Lecture9.pdf) of [UPenn's CIS 1890: Solving Hard Problems in Practice](https://www.cis.upenn.edu/~cis1890/).

### Periodicity

The periodic scheduling problem can be made simpler to solve with harmonic periods [(J Grus, C Hanen, Z Hanzálek; 2024)](https://arxiv.org/abs/2410.14756).

A simple script is provided to generate the harmonic period supersequences for a particular integer.

```bash
uv run harmonic_period_sequences.py 20

Harmonic Period Supersequences of 20:
[[20, 10, 5, 1], [20, 10, 2, 1], [20, 4, 2, 1]]
Divisors of 20:
[20, 10, 5, 4, 2, 1]
```

## Future Work

Currently, the solver that is used for this tool is OR-Tools' CP-SAT. In order to have a solver agnostic architecture, one can define the problem in [cpmpy](https://github.com/CPMpy/cpmpy).

From a problem space perspective, support for additional scheduling problems, such as ones with multiple machines, multi-stage jobs, preemption, other objectives, etc. can be added. This can be done by allowing the user to specify the scheduling problem in $\alpha|\beta|\gamma$ notation and provide the schedule problem data, from which the script can construct the appropriate variables, constraints, and objectives for the solver. Note that such a tool does not exist currently and probably hasn't existed yet due to how domain specific scheduling problems are typically constructed rather than in $\alpha|\beta|\gamma$ notation.
