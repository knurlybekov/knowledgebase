# Databases, Week 4: Normalization

## Normal forms
A relation is in first normal form when every attribute holds atomic values. Second normal form removes partial dependencies on a composite key. Third normal form removes transitive dependencies: every non-key attribute depends on the key, the whole key, and nothing but the key. Boyce-Codd normal form requires every determinant to be a candidate key.

## Decomposition
A lossless-join decomposition preserves the original relation when the shared attributes form a key of at least one part. Dependency preservation is not guaranteed by BCNF decomposition; the lecture example splits a schedule table into three relations and loses one functional dependency, which the instructor accepts for the course project.

## Course project
The term project must reach third normal form. BCNF is recommended but not required, and the instructor stated on 2026-02-10 that a documented exception for one dependency-preserving 3NF table is acceptable.
