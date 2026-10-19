# Algorithms, Lecture 6: Shortest paths

## Dijkstra's algorithm
Dijkstra's algorithm computes single-source shortest paths when every edge weight is non-negative. With a binary heap it runs in O((V + E) log V) time; with a Fibonacci heap the bound improves to O(E + V log V). The algorithm fails on graphs with negative edge weights because a settled vertex may later receive a shorter path.

## Bellman-Ford
Bellman-Ford handles negative edge weights and detects negative cycles. It relaxes every edge V - 1 times and runs in O(V E) time. The course recommends Bellman-Ford only when negative weights are present, because Dijkstra is faster on the common case.

## Exam note
The midterm asks for the correctness argument of Dijkstra (the cut property) and for a counterexample with a negative edge. Students must state the heap-based running time, not the array-based O(V^2) bound, unless the graph is dense.
