# Machine Learning, Lecture 8: Regularization and validation

## Ridge and lasso
Ridge regression adds an L2 penalty and shrinks coefficients toward zero without making them exactly zero. Lasso adds an L1 penalty and produces sparse coefficients, which makes it a feature selection method. Elastic net mixes both penalties with a parameter alpha between 0 and 1.

## Choosing the penalty strength
The penalty strength lambda is chosen by k-fold cross-validation. The course uses k = 5 by default and k = 10 for small data sets under 500 rows. Selecting lambda on the test set is a data leak and loses marks on the assignment.

## Assignment 3
Assignment 3 requires a comparison of ridge, lasso, and elastic net on the housing data set with 5-fold cross-validation, a plot of validation error against lambda, and a short justification of the final choice. The report is limited to four pages.
