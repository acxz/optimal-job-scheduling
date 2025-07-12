# /// script
# dependencies = [
#   "sympy",
# ]
# ///

import argparse
import pprint
import sympy

parser = argparse.ArgumentParser(
    description="""
Compute the harmonic period supersequences of an integer

Ex: uv run harmonic_period_sequences.py 20
""",
    epilog="""
A harmonic period sequence is defined as a sequence of numbers where each number can be divisible by an integer to obtain the next number in the sequence.
A harmonic period supersequence is defined as a sequence where other harmonic period sequences are captured within.
For example: the harmonic period sequences of 4 are [4, 2, 1] and [4, 1].
However, note that the sequence [4, 1], is a subsequence of the supersequence [4, 2, 1].
By some notion of "dual", the harmonic period sequence is sort of like the dual of a prime factorization tree, where each "path" in a prime factorization tree, corresponds to a harmonic period sequence.
""",
)

parser.add_argument(
    "n", type=int, help="integer to find the harmonic period supersequeces of"
)

args = parser.parse_args()
n = args.n

harmonic_period_supersequences = []


# The sequences are created by iterating through an integer's prime factors
# and appending the integer/primefactor value to the sequence
# This process is done recursively, so that every sequence (as an integer can
# have multiple prime factors) can be captured
def generate_harmonic_period_supersequences(current_sequence):
    current_n = current_sequence[-1]
    if current_n == 1:
        harmonic_period_supersequences.append(current_sequence)
    else:
        current_n_primefactors = sympy.primefactors(current_n)
        for next_n in current_n_primefactors:
            next_sequence = current_sequence + [current_n // next_n]
            generate_harmonic_period_supersequences(next_sequence)


generate_harmonic_period_supersequences([n])

print("Harmonic Period Supersequences of " + str(n) + ":")
pprint.pprint(harmonic_period_supersequences)

n_divisors = list(reversed(sympy.divisors(n)))
print("Divisors of " + str(n) + ": ")
print(n_divisors)
