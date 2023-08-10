import time

import click
from pysat.formula import CNF
from pysat.solvers import Solver

from common import *

print = click.echo

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"], max_content_width=999, show_default=True)


@click.command(context_settings=CONTEXT_SETTINGS)
@click.option("--cnf", "path_cnf", required=True, type=click.Path(exists=True), help="File with CNF")
@click.option("--backdoors", "path_backdoors", required=True, type=click.Path(exists=True), help="File with backdoors")
@click.option("-o", "--output", "path_output", type=click.Path(), help="Output file")
@click.option("--limit", "limit_backdoors", type=int, help="Number of backdoors to use (prefix size)")
@click.option("--add-units", "is_add_derived_units", is_flag=True, help="Add derived units to the solver")
@click.option(
    "--num-confl",
    type=int,
    default=0,
    show_default=True,
    help="Number of conflicts in 'solve_limited' (0 for using 'propagate')",
)
def cli(
    path_cnf,
    path_backdoors,
    path_output,
    limit_backdoors,
    is_add_derived_units,
    num_confl,
):
    time_start = time.time()

    print(f"Loading CNF from '{path_cnf}'...")
    cnf = CNF(from_file=path_cnf)
    print(f"CNF clauses: {len(cnf.clauses)}")
    print(f"CNF variables: {cnf.nv}")

    print()
    print(f"Loading backdoors from '{path_backdoors}'...")
    backdoors = parse_backdoors(path_backdoors)
    print(f"Total backdoors: {len(backdoors)}")
    if backdoors:
        print(f"First backdoor size: {len(backdoors[0])}")

    all_backdoors = backdoors
    if limit_backdoors is not None:
        print(f"Limiting to {limit_backdoors} backdoors")
        backdoors = backdoors[:limit_backdoors]

    unique_variables = sorted(multiunion(backdoors), key=abs)
    print(f"Total variables in {len(backdoors)} backdoors: {sum(map(len, backdoors))}")
    print(f"Unique variables in {len(backdoors)} backdoors: {len(unique_variables)}")

    print()
    is_using_solve_limited = num_confl > 0
    if is_using_solve_limited:
        print(f"Note: using 'propagate' and 'solve_limited({num_confl=})'")
        solver_limited = Solver("cadical153", bootstrap_with=cnf)
    else:
        print(f"Note: using 'propagate' only")

    rho_per_backdoor = []

    units_per_backdoor = []
    new_units_per_backdoor = []
    unique_units = set()

    binary_per_backdoor = []
    new_binary_per_backdoor = []
    unique_binary = set()

    ternary_per_backdoor = []
    new_ternary_per_backdoor = []
    unique_ternary = set()

    large_per_backdoor = []
    new_large_per_backdoor = []
    unique_large = set()

    with Solver("glucose42", bootstrap_with=cnf) as solver:
        for i, variables in enumerate(backdoors):
            print()
            print(f"=== [{i+1}/{len(backdoors)}] " + "-" * 42)

            # Convert to 1-based:
            variables = [v + 1 for v in variables]

            print(f"Backdoor with {len(variables)} variables: {variables}")

            print(f"Partioning tasks...")
            hard, easy = partition_tasks(solver, variables)
            assert len(hard) + len(easy) == 2 ** len(variables)
            print(f"Total 2^{len(variables)} = {2**len(variables)} tasks: {len(hard)} hard and {len(easy)} easy")

            if is_using_solve_limited:
                print(f"Determining semi-easy tasks using 'solve_limited({num_confl=})'...")
                time_start_semieasy = time.time()
                semieasy = determine_semieasy_tasks(solver_limited, hard, num_confl)
                print(f"... done in {time.time() - time_start_semieasy:.3f} s")
                print(f"Semi-easy tasks: {len(semieasy)}")
                easy += semieasy

            rho = len(easy) / 2 ** len(variables)
            print(f"rho = {len(easy)}/{2**len(variables)} = {rho}")
            rho_per_backdoor.append(rho)

            # print()
            print(f"Minimizing characteristic function...")
            clauses = backdoor_to_clauses_via_easy(variables, easy)

            units = sorted((c[0] for c in clauses if len(c) == 1), key=abs)
            units_per_backdoor.append(units)
            for unit in units:
                if -unit in unique_units:
                    raise RuntimeError(f"Wow! {unit}")
            new_units = [x for x in units if x not in unique_units]
            new_units_per_backdoor.append(new_units)
            unique_units.update(units)
            print(f"Derived {len(units)} ({len(new_units)} new) units: {units}")

            binary = sorted(tuple(sorted(c, key=abs)) for c in clauses if len(c) == 2)
            binary_per_backdoor.append(binary)
            new_binary = [x for x in binary if x not in unique_binary]
            new_binary_per_backdoor.append(new_binary)
            unique_binary.update(binary)
            print(f"Derived {len(binary)} ({len(new_binary)} new) binary clauses: {binary}")

            ternary = sorted(tuple(sorted(c, key=abs)) for c in clauses if len(c) == 3)
            ternary_per_backdoor.append(ternary)
            new_ternary = [x for x in ternary if x not in unique_ternary]
            new_ternary_per_backdoor.append(new_ternary)
            unique_ternary.update(ternary)
            print(f"Derived {len(ternary)} ({len(new_ternary)} new) ternary clauses: {ternary}")

            large = sorted(tuple(sorted(c, key=abs)) for c in clauses if len(c) > 3)
            large_per_backdoor.append(large)
            new_large = [x for x in large if x not in unique_large]
            new_large_per_backdoor.append(new_large)
            unique_large.update(large)
            print(f"Derived {len(large)} ({len(new_large)} new) large clauses: {large}")

            if is_add_derived_units:
                for unit in new_units:
                    solver.add_clause([unit])

    if is_using_solve_limited:
        solver_limited.delete()
        del solver_limited

    print()
    print("=" * 42)
    print()

    print(f"{rho_per_backdoor = }")
    print(f"{units_per_backdoor = }")
    print(f"{new_units_per_backdoor = }")
    print(f"{binary_per_backdoor = }")
    print(f"{new_binary_per_backdoor = }")
    print(f"{ternary_per_backdoor = }")
    print(f"{new_ternary_per_backdoor = }")
    print(f"{large_per_backdoor = }")
    print(f"{new_large_per_backdoor = }")

    if path_output:
        print()
        print(f"Writing results to '{path_output}'...")
        with open(path_output, "w") as f:
            for unit in unique_units:
                f.write(f"{unit} 0\n")
            for c in unique_binary:
                f.write(" ".join(map(str, c)) + " 0\n")
            for c in unique_ternary:
                f.write(" ".join(map(str, c)) + " 0\n")
            for c in unique_large:
                f.write(" ".join(map(str, c)) + " 0\n")

    print()
    print(f"Total variables in {len(backdoors)} backdoors: {sum(map(len, backdoors))}")
    print(f"Unique variables in {len(backdoors)} backdoors: {len(unique_variables)}")
    print(
        f"Total derived (non-unique) {sum(map(len, units_per_backdoor))} units, {sum(map(len, binary_per_backdoor))} binary, {sum(map(len, ternary_per_backdoor))} ternary, and {sum(map(len, large_per_backdoor))} larger clauses"
    )

    unique_units = sorted(unique_units, key=abs)
    print(f"Derived {len(unique_units)} unique units: {unique_units}")
    print(f"Derived {len(unique_binary)} unique binary")
    print(f"Derived {len(unique_ternary)} unique ternary")
    print(f"Derived {len(unique_large)} unique large")
    print(f"Total derived {len(unique_units)+len(unique_binary)+len(unique_ternary)+len(unique_large)} unique clauses")

    # print("New:")
    # for new_units in new_units_per_backdoor:
    #     print(f"  {new_units}")
    # print("Units:")
    # for units in units_per_backdoor:
    #     print(f"  {units}")

    print()
    print(f"All done in {time.time() - time_start:.1f} s")


if __name__ == "__main__":
    cli()

"""
### Simple Espresso minimization of CvK-12:
```
$ python scripts\minimize.py --cnf data\mult\lec_CvK_12.cnf --backdoors backdoors_CvK-12_1k.txt --limit 100
```
Total variables in 100 backdoors: 1000
Unique variables in 100 backdoors: 549
Total 60 unique derived units: [-45, -1854, -1902, -1908, -1982, -1994, -2076, -2095, -2163, -2233, -2606, -2654, -2660, -2734, -2746, -2828, -2847, -2915, -2985, -3444, -3456, -3538, -3557, -3625, -3695, -3787, -3874, -3876, -3885, -3899, -3900, -3901, 3902, -3905, -3910, -3911, -3912, -3923, -3976, -3977, -3980, -3989, -4003, -4005, -4020, -4022, -4042, -4071, -4077, -4090, -4158, -4228, -4260, -4265, -4271, -4273, -4383, -4475, -4534, -4540]

All done in 15.111 s


### With adding units to the solver (--add-units):
```
$ python scripts\minimize.py --cnf data\mult\lec_CvK_12.cnf --backdoors backdoors_CvK-12_1k.txt --limit 100 --add-units
```
Total variables in 100 backdoors: 1000
Unique variables in 100 backdoors: 549
Total 62 unique derived units: [-45, -1854, -1902, -1908, -1982, -1994, -2076, -2095, -2163, -2233, -2606, -2654, -2660, -2734, -2746, -2828, -2847, -2915, -2985, -3444, -3456, -3538, -3557, -3625, -3695, -3787, -3874, -3876, -3885, -3899, -3900, -3901, 3902, -3905, -3910, -3911, -3912, -3923, -3976, -3977, -3980, -3989, -4003, -4005, -4020, -4022, -4041, -4042, -4071, -4077, 4079, -4090, -4158, -4228, -4260, -4265, -4271, -4273, -4383, -4475, -4534, -4540]

All done in 15.579 s


### With 'solve_limited' (--num-confl):
```
$ python scripts\minimize.py --cnf data\mult\lec_CvK_12.cnf --backdoors backdoors_CvK-12_1k.txt --limit 100 --num-confl 1000
```
Total variables in 100 backdoors: 1000
Unique variables in 100 backdoors: 549
Total 91 unique derived units: [-45, -1848, -1854, -1902, -1908, -1982, -1994, -2070, -2076, -2095, -2163, -2233, -2396, -2460, -2471, -2606, -2654, -2660, -2734, -2746, -2799, -2813, -2823, -2828, -2833, -2834, -2847, -2915, -2957, -2985, -3014, -3148, -3212, -3444, -3456, -3538, -3557, -3625, -3695, -3787, -3874, -3876, -3885, -3899, -3900, -3901, 3902, -3905, -3910, -3911, -3912, -3923, -3947, -3968, -3971, -3972, -3973, -3976, -3977, 3979, -3980, -3989, -4003, -4005, -4020, -4022, -4041, -4042, -4070, -4071, -4077, 4079, -4082, -4086, -4090, -4158, -4211, -4228, -4249, -4260, 4263, -4265, -4271, -4273, -4383, -4475, -4534, -4540, -4656, -5129, -5440]

All done in 526.058 s


------------------------------------------------------------------------------
(same, but with 1000 backdoors)


### Simple Espresso minimization of CvK-12:
```
$ python scripts\minimize.py --cnf data\mult\lec_CvK_12.cnf --backdoors backdoors_CvK-12_1k.txt --limit 1000
```
Total variables in 1000 backdoors: 10000
Unique variables in 1000 backdoors: 2503
Total 86 unique derived units: [-45, -1848, -1854, -1902, -1908, -1982, -1994, -2070, -2076, -2082, -2095, -2163, -2233, -2396, -2600, -2606, -2654, -2660, -2734, -2746, -2822, -2828, -2834, -2847, -2915, -2985, -3444, -3456, -3538, -3544, -3557, -3625, -3695, -3781, -3787, -3874, -3876, -3885, -3890, -3899, -3900, -3901, 3902, -3905, -3907, -3910, -3911, -3912, 3913, 3914, -3923, -3976, -3977, -3978, -3980, -3989, -4003, -4005, -4020, -4022, -4041, -4042, -4051, -4065, -4066, -4071, -4076, -4077, 4079, -4090, -4143, -4158, -4228, -4251, -4260, -4262, -4265, -4271, -4273, -4293, -4383, -4475, -4534, -4540, -4542, -5439]

All done in 178.135 s


### With adding units to the solver (--add-units):
```
$ python scripts\minimize.py --cnf data\mult\lec_CvK_12.cnf --backdoors backdoors_CvK-12_1k.txt --limit 1000 --add-units
```
Total variables in 1000 backdoors: 10000
Unique variables in 1000 backdoors: 2503
Total 99 unique derived units: [-45, -1848, -1854, -1902, -1908, -1982, -1994, -2070, -2076, -2082, -2095, -2163, -2233, -2396, -2600, -2606, -2654, -2660, -2734, -2746, -2822, -2828, -2834, -2847, -2915, -2985, -3444, -3456, -3532, -3533, -3538, -3544, -3557, -3625, -3695, -3781, -3787, -3874, -3876, -3885, -3890, -3899, -3900, -3901, 3902, 3903, -3905, -3907, -3910, -3911, -3912, 3913, 3914, -3923, -3972, -3976, -3977, -3978, 3979, -3980, -3989, -4003, -4005, -4020, -4022, -4041, -4042, 4044, -4051, -4056, -4060, -4065, -4066, 4068, 4069, -4071, -4076, -4077, -4078, 4079, -4090, -4139, -4143, -4158, -4228, -4251, -4254, -4260, -4262, -4265, -4271, -4273, -4293, -4383, -4475, -4534, -4540, -4542, -5439]

All done in 176.747 s

"""

# BvP-8-4
"""
$ python scripts\minimize.py --cnf data\instances\miters\cnf-fraig\BvP_8_4-aigmiter-fraig-aigtocnf.cnf --backdoors backdoors_BvP-8-4_1k.txt --limit 100
Total variables in 100 backdoors: 1000
Unique variables in 100 backdoors: 561
Total 0 unique derived units: []

All done in 18.8 s


$ python scripts\minimize.py --cnf data\instances\miters\cnf-fraig\BvP_8_4-aigmiter-fraig-aigtocnf.cnf --backdoors backdoors_BvP-8-4_1k.txt --limit 100 --num-confl 100
Total variables in 100 backdoors: 1000
Unique variables in 100 backdoors: 561
Total 1 unique derived units: [-4248]

All done in 714.6 s

"""
