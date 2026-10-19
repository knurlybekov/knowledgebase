# Algorithms, Lecture 11: Dynamic programming

## Principle
A problem has optimal substructure when an optimal solution contains optimal solutions to subproblems, and overlapping subproblems when the same subproblem recurs. Dynamic programming stores each subproblem's answer once.

## Longest common subsequence
LCS of two strings of lengths m and n fills an (m + 1) by (n + 1) table in O(m n) time and O(m n) space; space drops to O(min(m, n)) when only the length is required. The assignment in week 12 asks for the reconstruction of one LCS, which needs the full table or Hirschberg's divide-and-conquer.

## Change of recommendation
In Lecture 6 the course treated memoized recursion as the preferred form. From this lecture on, the bottom-up table is the recommended form for exam answers because it makes the running time explicit. Memoization remains acceptable when the recurrence is stated and the number of distinct states is bounded.
