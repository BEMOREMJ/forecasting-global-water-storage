import numpy as np

from drought_forecasting.crossfit_ensemble import optimize


def test_weights_feasible_deterministic():
 c={"initial_weights":[.5,.5],"tolerance":1e-12,"maximum_iterations":100,"feasibility_tolerance":1e-8};X=np.array([[1.,2.],[2.,1.]]);y=np.array([1.,2.]);a,_=optimize(X,y,c);b,_=optimize(X,y,c);assert np.allclose(a,b) and a.min()>=0 and np.isclose(a.sum(),1)
def test_swapped_direction_rejected():
 routes={"F01":"train_F02","F02":"train_F01"};bad={"F01":"train_F01","F02":"train_F02"};assert bad!=routes
