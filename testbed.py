
import numpy as np
import random
import pandas as pd
import statsmodels.api as sm
from scipy.stats import norm


def Synthetic(Y_c, Y_t, X_c, X_t, return_individual=False):

	"""
	Function that performs synthetic control estimates of individual
	treatment effect for each treated unit.

	For each treated unit, we find w that minimizes:
		|| w' X_c - X_t ||^2.

	Since the number of controls should always be greater than the number of
	covariates, the linear system is underdetermined, and least squares	is
	used to obtain a solution w.

	Args:
		Y_c = N_c-dimensional array of control unit outcomes
		Y_t = N_t-dimensional array of treated unit outcomes
		X_c = N_c-by-k matrix of control units
		X_t = N_t-by-k matrix of treated units
		return_individual = Boolean indicating whether vector of individual
		                    treatment effects should be returned

	Returns:
		ATT = Scalar value of estaimted average treatment effect on the treated
		ITT = N_t-dimensional array of estimated individual treatment effects
		      for the treated sample
	"""

	N_c, N_t = len(Y_c), len(Y_t)

	ITT = np.zeros(N_t)

	for i in xrange(N_t):
		w = np.linalg.lstsq(X_c.T, X_t[i, ])[0]  # regress X_t[i] on X_c matrix
		ITT[i] = Y_t[i] - np.dot(w, Y_c)

	if return_individual:
		return ITT.mean(), ITT
	else:
		return ITT.mean()


def SyntheticEstimates(Y, D, X, higher_moments=False):

	"""
	Function that computes ATT estimates from observerd data using
	synthetic control method.

	If higher_moments is true, then matching with be done on higher
	moments of X as well. For now this only includes absolute first
	moments, and second moments.

	Args:
		Y = N-dimensional array of observed outcomes
		D = N-dimensional array of treatment indicator; 1=treated, 0=control
		X = N-by-k matrix of covariates
		higher_moments = Boolean indicating whether to match on higher
		                 moments of X as well

	Returns:
		ATT estimate
	"""

	control = (D == 0)  # Boolean index of control units
	treated = (D == 1)  # Boolean index of treated units
	if higher_moments:
		X_control = np.hstack((X[control], abs(X[control]), X[control]**2))
		X_treated = np.hstack((X[treated], abs(X[treated]), X[treated]**2))
		return Synthetic(Y[control], Y[treated], X_control, X_treated)
	else:
		return Synthetic(Y[control], Y[treated], X[control], X[treated])


def MatchingWithReplacement(Y, D, X, mahalanobis=True, bias_correction=True):

	"""
	Function that estimates the average treatment effect for the treated (ATT)
	using matching with replacement.

	To perform bias correction, we estimate the bias term by
		B = beta_c * (X_t - X_c[matched]),
	where beta_c is the slope coefficient from the regression
		Y_c[matched] = alpha_c + beta_c * X_c[matched] + epsilon.
	For details, see Imbens-Rubin.

	Args:
		Y = N-dimensional array of observed outcomes
		D = N-dimensional array of treatment indicator; 1=treated, 0=control
		X = N-by-k matrix of covariates
		mahalanobis = Boolean indicating whether to use Mahalanobis metric
		              to measure covariate difference or not
		bias_correction = Boolean indicating whether to perform bias correction
		                  based on separate regressions on levels of covariates

	Returns:
		ATT estimate
	"""

	Y_c, Y_t, X_c, X_t = Y[D==0], Y[D==1], X[D==0], X[D==1]

	N_t = len(Y_t)

	match_index = np.zeros(N_t, dtype=np.int)

	if mahalanobis:
		V = np.cov(X, rowvar=0)  # rowvar=0 since each column of X is a variable
		for i in xrange(N_t):
			dX = X_c - X_t[i]  # N_c-by-k matrix of covariate differences
			# calculate quadratic form dX_i' V dX_i for each i, then find min
			match_index[i] = (dX.dot(np.linalg.inv(V))*dX).sum(axis=1).argmin()
	else:
		for i in xrange(N_t):
			dX = X_c - X_t[i]  # N_c-by-k matrix of covariate differences
			match_index[i] = (dX**2).sum(axis=1).argmin()  # Euclidean norm

	if bias_correction:
		reg = sm.OLS(Y_c[match_index], sm.add_constant(X_c[match_index])).fit()
		ITT = Y_t - Y_c[match_index] - np.dot((X_t - X_c[match_index]),
		                                      reg.params[1:])
	else:
		ITT = Y_t - Y_c[match_index]

	return ITT.mean()  # return ITT.std() as well for standard errors


def MatchingWithoutReplacement(Y, D, X, mahalanobis=True, bias_correction=True):

	"""
	Function that estimates the average treatment effect for the treated (ATT)
	using matching without replacement.

	Since finding best matches for all treated units simultaneously in one go
	is combinatorial computationally, function uses a greedy algorithm where
	the best match is found (and then removed from the pool) for each treated
	unit, thus taking only linear time each time. The order in which the
	matching is done is based on estimated propensity score - see Imbens-Rubin
	for details.

	To perform bias correction, we estimate the bias term by
		B = beta_c * (X_t - X_c[matched]),
	where beta_c is the slope coefficient from the regression
		Y_c[matched] = alpha_c + beta_c * X_c[matched] + epsilon.
	For details, see Imbens-Rubin.

	Function swtiches to matching with replacement if number of control units
	is less than number of treated units.

	Args:
		Y = N-dimensional array of observed outcomes
		D = N-dimensional array of treatment indicator; 1=treated, 0=control
		X = N-by-k matrix of covariates
		mahalanobis = Boolean indicating whether to use Mahalanobis metric
		              to measure covariate difference or not
		bias_correction = Boolean indicating whether to perform bias correction
		                  based on separate regressions on levels of covariates

	Returns:
		ATT estimate
	"""

	if 2*sum(D) > len(D):  # if N_t > N_c
		print 'Not enough control units, matching with replacement instead.'
		return MatchingWithReplacement(Y, D, X, mahalanobis)

	pscore = sm.Logit(D, X).fit(disp=False).predict()  # estimate pscore with logit
	order = np.argsort(pscore)[::-1]  # sort pscore in descending order, get index
	Y, D, X = Y[order], D[order], X[order]  # sort data in order of pscore

	Y_c, Y_t, X_c, X_t = Y[D==0], Y[D==1], X[D==0], X[D==1]

	N_c, N_t = len(Y_c), len(Y_t)

	match_index = np.zeros(N_t, dtype=np.int)  # index of matched control units

	if mahalanobis:
		V = np.cov(X, rowvar=0)  # rowvar=0 since each column of X is a variable
		for i in xrange(N_t):
			dX = X_c - X_t[i]  # N_c-by-k matrix of covariate differences
			# calculate quadratic form dX_i' V dX_i for each treated i, then find min
			match_index[i] = np.nanargmin((dX.dot(np.linalg.inv(V))*dX).sum(axis=1))
			X_c[match_index[i]] = np.nan  # remove matched control unit with nan
			# don't want to actually remove matched unit from X_c since that
			# would mess up the indices and future computations involving X_c
	else:  # do same thing as above, just use different metric
		for i in xrange(N_t):
			dX = X_c - X_t[i]
			match_index[i] = np.nanargmin((dX**2).sum(axis=1))  # Euclidean norm
			X_c[match_index[i]] = np.nan

	if bias_correction:
		X_c = X[D==0]  # redefine X_c to replace nan values created earlier
		reg = sm.OLS(Y_c[match_index], sm.add_constant(X_c[match_index])).fit()
		ITT = Y_t - Y_c[match_index] - np.dot((X_t - X_c[match_index]),
		                                      reg.params[1:])
	else:
		ITT = Y_t - Y_c[match_index]

	return ITT.mean()  # return ITT.std() as well for standard errors


def MatchingEstimates(Y, D, X, with_replacement=True, mahalanobis=True):

	"""
	Function that estimates the average treatment effect for the treated (ATT)
	using matching.

	Can specify whether matching is done with or without replacement. Swtiches
	to matching with replacement if number of control units is less than
	number of treated units.

	Args:
		Y = N-dimensional array of observed outcomes
		D = N-dimensional array of treatment indicator; 1=treated, 0=control
		X = N-by-k matrix of covariates

	Returns:
		ATT estimate; matching done with or without replacement as specified
	"""

	if with_replacement:
		return MatchingWithReplacement(Y, D, X, mahalanobis)
	else:
		return MatchingWithoutReplacement(Y, D, X, mahalanobis)


def OLSEstimates(Y, D, X):

	"""
	Function that estimates average treatment effect for the treated (ATT)
	using OLS, which is consistent when the true model is linear.

	Args:
		Y = N-dimensional array of observed outcomes
		D = N-dimensional array of treatment indicator; 1=treated, 0=control
		X = N-by-k matrix of covariates

	Returns:
		ATT estimate
	"""

	k = X.shape[1]
	D = D.reshape((D.size, 1))  # convert D into N-by-1 vector
	dX = X - X.mean(0)  # demean covariates
	DdX = D * dX
	# construct design matrix
	W = np.column_stack((D, dX, DdX))

	reg = sm.OLS(Y, sm.add_constant(W)).fit()

	# for derivation of this estimator, see my notes on Treatment Effects
	return reg.params[1] + np.dot((DdX.sum(0) / D.sum()), reg.params[-k:])


class parameters:

	"""
	Class object that stores the parameter values for use in the baseline model.
	
	See SimulateData function for model description.

	Args:
		N = Sample size (control + treated units) to generate
		k = Number of covariates
	"""

	def __init__(self, N=500, k=3):  # set initial parameter values
		self.N = N  # sample size (control + treated units)
		self.k = k  # number of covariates

		self.delta = 3
		self.beta = np.ones(k)
		self.theta = np.ones(k)
		self.mu = np.zeros(k)
		self.Sigma = np.identity(k)
		self.Gamma = np.identity(2)


def SimulateData(para=parameters(), nonlinear=False, return_counterfactual=False):

	"""
	Function that generates data according to one of two simple models that
	satisfies the Unconfoundedness assumption.

	The covariates and error terms are generated according to
		X ~ N(mu, Sigma), epsilon ~ N(0, Gamma).
	The counterfactual outcomes are generated by
		Y_0 = X*beta + epsilon_0,
		Y_1 = delta + X*(beta+theta) + epsilon_1,
	if the nonlinear Boolean is False, or by
		Y_0 = sum_of_abs(X) + epsilon_0,
		Y_1 = sum_of_squares(X) + epsilon_1,
	if the nonlinear Boolean is True.

	Selection is done according to the following propensity score function:
		P(D=1|X) = Phi(X*beta),
	where Phi is the standard normal CDF.

	Args:
		para = Model parameter values supplied by parameter class object
		nonlinear = Boolean indicating whether the data generating model should
		            be linear or not
		return_counterfactual = Boolean indicating whether to return vectors of
		                        counterfactual outcomes

	Returns:
		Y = N-dimensional array of observed outcomes
		D = N-dimensional array of treatment indicator; 1=treated, 0=control
		X = N-by-k matrix of covariates
		Y_0 = N-dimensional array of non-treated outcomes
		Y_1 = N-dimensional array of treated outcomes
	"""

	k = len(para.mu)

	X = np.random.multivariate_normal(mean=para.mu, cov=para.Sigma,
	                                  size=para.N)
	epsilon = np.random.multivariate_normal(mean=np.zeros(2), cov=para.Gamma,
	                                        size=para.N)

	Xbeta = np.dot(X, para.beta)

	pscore = norm.cdf(Xbeta)
	# for each p in pscore, generate Bernoulli rv with success probability p
	D = np.array([np.random.binomial(1, p, size=1) for p in pscore]).flatten()

	if nonlinear:
		Y_0 = abs(X).sum(1) + epsilon[:, 0]
		Y_1 = (X**2).sum(1) + epsilon[:, 1]
	else:
		Y_0 = Xbeta + epsilon[:, 0]
		Y_1 = para.delta + np.dot(X, para.beta+para.theta) + epsilon[:, 1]

	Y = (1 - D) * Y_0 + D * Y_1  # compute observed outcome

	if return_counterfactual:
		return Y, D, X, Y_0, Y_1
	else:
		return Y, D, X


def MonteCarlo(B=500, para=parameters(), nonlinear=False, print_progress=True):

	"""	
	Function that returns ATT estimates using synthetic control, matching,
	and OLS computed over B repetitions on simulated data.

	See SimulateData function for data generating process.

	Args:
		B = Number of Monte Carlo simulations to perform
		para = Model parameter values supplied by parameter class object
		nonlinear = Boolean indicating whether the data generating model should
		            be linear or not
		print_progress = Boolean indicating whether to dispaly current number
		                 of completed repetitions (every 10 repetitions)

	Returns:
		ATT_true = Actual average treatment effect for the treated
		ATT_syn = Estimated ATT using synthetic controls
		ATT_match = Estimated ATT using matching
		ATT_ols = Estimated ATT using OLS
	"""

	ATT_true = np.zeros(B)
	ATT_syn = np.zeros(B)
	ATT_match = np.zeros(B)
	ATT_ols = np.zeros(B)

	for i in xrange(B):

		Y, D, X, Y_0, Y_1 = SimulateData(para, nonlinear, True)

		ATT_true[i] = (Y_1[D==1]-Y_0[D==1]).mean()
		ATT_syn[i] = SyntheticEstimates(Y, D, X, higher_moments=nonlinear)
		ATT_match[i] = MatchingEstimates(Y, D, X, with_replacement=True)
		ATT_ols[i] = OLSEstimates(Y, D, X)

		if print_progress and (i+1) % 10 == 0:
			print i+1, 'out of', B, 'simulations completed.'

	return ATT_true, ATT_syn, ATT_match, ATT_ols


def CalculateMSE(B=500, para=parameters(), nonlinear=False):

	"""
	Function that calcuates MSE after performing Monte Carlo simulations.

	Args:
		B = Number of Monte Carlo simulations to perform
		para = Model parameter values supplied by parameter class object
		nonlinear = Boolean indicating whether the data generating model should
		            be linear or not

	Returns:
		MSE_syn = Estimated MSE using synthetic control estimates
		MSE_match = Estimated MSE using matching estimates
		MSE_ols = Estimated MSE using OLS estimates
	"""

	ATT_true, ATT_syn, ATT_match, ATT_ols = MonteCarlo(B, nonlinear=nonlinear)

	MSE_syn = ((ATT_syn - ATT_true)**2).mean()
	MSE_match = ((ATT_match - ATT_true)**2).mean()
	MSE_ols = ((ATT_ols - ATT_true)**2).mean()

	return MSE_syn, MSE_match, MSE_ols


def UseLalondeData():

	"""
	Utility function that reads and applies synthetic control
	estimator on Lalonde's NSW experimental data.

	Note that because of complete randomization, the mean
	difference identifies both the ATE and ATT.
	"""

	url = 'http://www.stanford.edu/~lwong1/data.csv'
	lalonde = pd.read_csv(url)  # read CSV data from url

	covariate_list = ['age', 'education', 'black', 'hispanic', 'married',
	                  'nodegree', 're74', 're75', 'u74', 'u75']

	# don't know how to not convert to array first
	Y = np.array(lalonde['re78'])
	D = np.array(lalonde['treat'])
	X = np.array(lalonde[covariate_list])
	
	ATT_syn = SyntheticEstimates(Y, D, X)
	ATT_match = MatchingEstimates(Y, D, X)
	ATT_ols = OLSEstimates(Y, D, X)

	print "Using Lalonde's National Supported Work (NSW) experimental data..."
	print 'Estimated ATT using synthetic control estimator:', ATT_syn
	print 'Estimated ATT using matching (with replacement) estimator:', ATT_match
	print 'Estimated ATT using OLS estimator:', ATT_ols
	print 'Mean difference:', Y[D==1].mean() - Y[D==0].mean()


def main():

	#UseLalondeData()

	B = 500
	print '\n' + 'Performing Monte Carlo simulations with B =', B
	MSE_syn, MSE_match, MSE_ols = CalculateMSE(B, nonlinear=True)
	print 'Estimated Mean Squared Error for matching estimator:', MSE_match
	print 'Estimated Mean Squared Error for synthetic control estimator:', MSE_syn
	print 'Estimated Mean Squared Error for OLS estimator:', MSE_ols


if __name__ == '__main__':
	main()
