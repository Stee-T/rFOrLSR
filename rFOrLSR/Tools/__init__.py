import re # regexp for the RegressorParser
import scipy.signal as sps
import numpy as np
import tqdm
import torch as tor

import matplotlib.pyplot as plt
from matplotlib import patches # for the Unit circle of zPlanePlot
plt.style.use( 'dark_background' ) # black graphs

# Library internal imports from sibling folders
from .. import CTors
from .. import HelperFuncs as HF

################################################################################################################################################
####                                                                                                                                       #####
####                                                     (Linear) IIR Analysis Tools                                                       #####
####                                                                                                                                       #####
################################################################################################################################################

# ############################################################### FOrLSR to IIR #############################################################
def rFOrLSR2IIR( theta, L, RegNames ):
  """Converts the FOrLSR Output into a a,b IIR filter coefficient vectors.
  There is no guarantee on the order of the regressors so some matching is required. Additionally, y[k-j] terms are sign flipped (IIR convention).
  
  ### Inputs:
  - `theta`: (1D float iterable) containing the regression coefficients
  - `L`: (1D int iterable) containing the selected regressor indices
  - `RegNames`: (1D string iterable) containing the regressor names

  ### Outputs:
  - `b`: (1D float np.array) containing the b (numerator) coefficients
  - `a`: (1D float np.array) containing the a (denominator) coefficients
  """

  def RegressorParser( term ):
    
    pattern = re.compile( r'([xy])\[(k-\d+)\]' ) # Regexpr pattern to match terms like x[k-j] or y[k-j]

    # Special case for x[k-0]
    if ( term == 'x[k]' ): return ( 'x', 0 )
    
    match = pattern.match( term )
    if ( match ):
      # Extract the variable (x or y) and the delay (j)
      variable, delay = match.groups()
      delay = int( delay.split( '-' )[1] )
      return ( variable, delay )
    
    raise ValueError( f"Invalid term: { term }. This function is only for linear IIRs (→ x[k-j], y[k-j] terms)" )

  # Parse regressor names
  CoeffList = []
  for i in range( len( theta ) ):
    variable, delay = RegressorParser( RegNames[ L[i] ] )
    CoeffList.append( ( theta[i], variable, delay ) )

  # first we need to find the respective maximum lags for x and y
  MaxLag = max( [ CoeffList[i][2] for i in range( len( CoeffList ) ) ] ) # get max delay

  # + 1 for x/y[k]
  a = np.zeros( MaxLag + 1, dtype = float ); a[0] = 1.0 # y[k]/a0 is normed due to FOrLSR structure
  b = np.zeros( MaxLag + 1, dtype = float ) # for x[k]

  for i in range( len( CoeffList ) ):
    if ( CoeffList[i][1] == 'x' ): b[ CoeffList[i][2] ] = CoeffList[i][0]
    if ( CoeffList[i][1] == 'y' ): a[ CoeffList[i][2] ] = - CoeffList[i][0] # - since in the regressions the y terms are on the other side

  return ( b, a )


#   ############################################################### IIR Spectrum #############################################################
def IIR_Spectrum( b_a_List = None, h_List = None, FilterNames = None, Fs = 44_100, Resolution = 5_000, xLims = None, yLimMag = None ):
  """Plots the magnitude and phase spectrum of the passed IIR-filters.
  The Magnitude response if plotted as: 20 * np.log10( np.maximum( abs( h ), 1e-06 ) ) to avoid zero-division warnings
  
  ### Inputs:
  - `b_a_List`: List of 2D-tuples containing (b, a) filter coefficients with ba dn a being iterables
  - `h_List`: List of 1D-iterables containing the complex frequency response
  - `FilterNames`: List of strings containing the filter names
  - `Fs`: (int / float = 44_100) containing the Sampling frequency
  - `Resolution`: (int = 5_000) containing the plot's resolution of the frequency axis
  - `xLims`: (2D-iterable of floats/ints = [1, Fs / 2]) containing the x-axis limits (1 since logarithmic)
  - `yLimMag`: (2D-iterable of floats/ints = [0, 1]) containing the y-axis limits of the magnitude plot
  
  ### Outputs:
  - `Fig`: Figure object containing the plot
  - `Ax`: Axes object containing the plot
  """
  # ***************************************************** Input checking *****************************************************
  if   ( ( b_a_List is None ) and ( h_List is not None ) ): CoeffList = h_List;   Coeff_Type = "h"
  elif ( ( b_a_List is not None ) and ( h_List is None ) ): CoeffList = b_a_List; Coeff_Type = "b_a"
  else: raise ValueError( "Either b_a_List or h_List must be passed" ) # covers case that both are not None or both are None

  if ( len( CoeffList ) < 1 ): raise ValueError( "CoeffList must contain at least one filter" )
  if ( not isinstance( CoeffList, list) ): raise ValueError( "CoeffList must be a list" )

  if ( Coeff_Type == "b_a" ):
    if ( not all( [ ( isinstance( CoeffList[i], ( tuple, list ) ) and len( CoeffList[i] ) == 2 ) for i in range( len( CoeffList ) ) ] ) ):
      raise ValueError( "b_a_List must be a list of 2D-tuples" )
  else: # Coeff_Type == "h"
    if ( not all( [ isinstance( CoeffList[i], ( np.ndarray, tuple, list ) ) for i in range( len( CoeffList ) ) ] ) ):
      raise ValueError( "CoeffList must be a list of numpy arrays" )

  if ( type( Fs ) not in [ int, float ] ): raise ValueError( "Fs must be an integer or float" )
  if ( Fs < 1 ): raise ValueError( "Fs must be a positive integer" )
  if ( Resolution < 1 ): raise ValueError( "Resolution must be a positive integer" )

  if ( FilterNames is None ): FilterNames = [ f'Filter {i + 1}' for i in range( len( CoeffList ) ) ]
  else:
    if ( len( CoeffList ) != len( FilterNames ) ): raise ValueError( "CoeffList and FilterNames must have the same length" )

  if ( xLims is None ): xLims = [ 1, Fs / 2 ]

  if ( yLimMag is None ):
    UpdateLowLim = True; UpdateHighLim = True
    yLimMag = [ np.inf, -np.inf ] # lowest values to be updated
  else: # respect only the user-imposed limits
    if ( yLimMag[0] is None ): UpdateLowLim = True; yLimMag[0] = np.inf
    else: UpdateLowLim = False

    if ( yLimMag[1] is None ): UpdateHighLim = True; yLimMag[1] = -np.inf
    else: UpdateHighLim = False

  # ************************************************************** Plots **************************************************************
  Fig, Ax = plt.subplots( 2, 1, sharex = True )
  Ax[0].set_title( 'Frequency Response' ) # randomly Ax[0], Ax[1] also valid

  # Prepare magnitude response
  Ax[0].set_xlabel( 'Frequency [Hz]' )
  Ax[0].set_xlim( xLims )
  # yLim is set after the loop, as there the min and max can be updated
  Ax[0].set_ylabel( 'Magnitude [dB]' )
  Ax[0].grid( which = 'both', alpha = 0.2 )

  # Prepare phase response
  Ax[1].set_xlabel( 'Frequency [Hz]' )
  Ax[1].set_ylabel( 'Phase [Radians]' )
  Ax[1].grid( which = 'both', alpha = 0.2 )

  # Plot the actual frequency responses
  for coeffs in CoeffList:

    if ( Coeff_Type == "b_a" ):
      w, h = sps.freqz( coeffs[0], coeffs[1], worN = Resolution, fs = Fs ) # expect b then a coeffs
    else: # Coeff_Type == "h"
      w = np.linspace( 0, Fs / 2, Resolution, endpoint = True )
      h = coeffs

    Magnitude = 20 * np.log10( np.maximum( abs( h ), 1e-06 ) )
    
    if ( UpdateLowLim ):  yLimMag[0] = np.min( ( yLimMag[0], np.min( Magnitude ) ) )
    if ( UpdateHighLim ): yLimMag[1] = np.max( ( yLimMag[1], np.max( Magnitude ) ) )

    # plot
    Ax[0].semilogx( w, Magnitude )
    Ax[1].semilogx( w, np.unwrap( np.angle( h ) ) )
  
  # add small margins for aesthetics
  if ( UpdateLowLim ):  yLimMag[0] = yLimMag[0] - 2
  if ( UpdateHighLim ): yLimMag[1] = yLimMag[1] + 2
  Ax[0].set_ylim( yLimMag[0], yLimMag[1] )

  Ax[0].legend( FilterNames )
  Ax[1].legend( FilterNames )

  Fig.tight_layout()

  return ( Fig, Ax )


#   ############################################################### zPlanePlot #############################################################
def zPlanePlot( b, a = 1, Title = None ):
  """Plot the poles and zeros of the passed filter in the z-plane.
  
  ### Inputs:
  - `b`: (1D np.array) containing numerator coefficients
  - `a`: (Optional: 1D np.array or 1 if nothing passed) containing denominator coefficients
  - `Title`: (str) containing figure title
  
  ### Outputs:
  - `z`: (1D complex np.array) containing zeros
  - `p`: (1D complex np.array) containing poles
  - `k`: (float) containing gain
  """

  Fig, Ax = plt.subplots()
  if ( Title is not None ): Fig.suptitle( Title )

  Ax.add_patch( patches.Circle( (0,0), radius = 1, fill = False, ls = 'dashed' ) ) # Unit circle

  # Normalize the coeficients if below 1
  k_num = max( 1.0, np.max( b ) )
  b /= k_num
  k_denom = max( 1.0, np.max( a ) )
  a /= k_denom
        
  # Compute poles and zeros
  z = np.roots( b ) # Zeros
  p = np.roots( a ) # Poles
  k = k_num / k_denom # Gain
    
  # Plot the zeros and set marker properties    
  Ax.plot( z.real, z.imag, 'go', ms = 10 )
  Ax.plot( p.real, p.imag, 'rx', ms = 10 )

  # Plot Cartesian grid
  Ax.spines['bottom'].set_position( 'zero' ) # move bottom line to center (real axis)
  Ax.spines['left'].set_position( 'zero' ) # move left line to center (imaginary axis)
  Ax.spines['top'].set_visible( False ) # hide top line
  Ax.spines['right'].set_visible( False ) # hide right line
  Ax.grid( which = 'both', alpha = 0.15 )
  Ax.axis( 'scaled' ) # square plot

  # Set limits and ticks: find the most far away zero/pole for scale
  Lim = 0.1 + max( 1, np.max( np.abs( z ) ), np.max( np.abs( p ) ) ) # minimum of 1.1 to include UC
  Ax.set_xlim( -Lim, Lim ); Ax.set_ylim( -Lim, Lim )

  # declutter the axis if many ticks. Safeguard for Matplotlib taking ages and tons of RAM
  if   ( Lim >= 100 ): TickSpacing = 100 # pretty instable filter though :P
  elif ( Lim >= 50 ):  TickSpacing = 10
  elif ( Lim >= 25 ):  TickSpacing = 5
  elif ( Lim >= 10 ):  TickSpacing = 2
  elif ( Lim >= 5 ):   TickSpacing = 1
  elif ( Lim >= 1.5 ): TickSpacing = 0.5
  else:                TickSpacing = 0.25

  nTicks = int( Lim / TickSpacing ) # floored entire number of ticks on one side
  FurthestTick = TickSpacing * ( nTicks + 1 )

  # set the ticks
  ticks = np.arange( -FurthestTick, FurthestTick + TickSpacing, TickSpacing ) # + Tickspacing: same amount on both sides
  Ax.set_xticks( ticks ); Ax.set_yticks( ticks )
  
  Fig.tight_layout()

  return ( z, p, k )


################################################################################################################################################
####                                                                                                                                       #####
####                                                      Non-Linear Analysis Tools                                                        #####
####                                                                                                                                       #####
################################################################################################################################################

# ############################################################################ Variable Selection Procedure #############################################################################
def ComputeERR( y, Ds ):
  ''' Imposed only part of the rFOrLSR, as only the ERR of imposed terms is computed and returned.
  
  ### Inputs:
  - `y`: (1D torch.Tensor) containing the system output vector
  - `Ds`: (2D torch.Tensor) containing the imposed terms

  ### Outputs:
  - `ERR`: (np.array of float) containing the error reduction ratio (ERR) of the imposed terms in the same order as Ds
  '''

  s2y = ( y @ y ).item() # mean free observation empiric variance
  ERR = np.full( Ds.shape[1], 0.0, dtype = np.float64 ) # list of Error reduction ratios of all imposed regressors
  Psi = tor.empty( ( len( y ), 0 ) ); Psi_n = tor.empty( ( len( y ), 0 ) ) # Create empty ( p, 0 )-sized matrices to simplify the code below

  # First iteration treated separately since no orthogonalization and no entry in A, and requires some reshapes
  Psi = Ds[:, 0, None] # unnormed orthogonal regressor matrix ( already centered ) reshaped as column
  n_Omega = HF.Norm2( Psi ) # squared euclidean norm of Omega or fudge factor
  Psi_n = Psi / n_Omega # normed orthogonal regressor matrix
  ERR[0] = ( ( Psi_n.T @ y ).item() )**2 * n_Omega / s2y # W[-1]^2 * n_Omega/s2y ) as usual but without storing W
  
  for col in range( 1, Ds.shape[1] ): # iterate over columns, start after position 1
    if ( np.sum( ERR[:col] ) >= 1 ): return ( ERR ) # R[1/2] early exit if max ERR reached, array is init with 1s
    # Computations
    Omega = Ds[:, col] - Psi_n @ ( Psi.T @ Ds[:, col] ) # orthogonalize only the current column ( no reshape needed )
    n_Omega = HF.Norm2( Omega )  # squared euclidean norm of Omega or fudge factor
    ERR[col] = ( ( Omega @ y ).item() / n_Omega )**2 * n_Omega / s2y # W[-1]^2 * n_Omega/s2y ) as usual but without storing W
    
    # Data storage, add current regressor
    Psi = tor.column_stack( ( Psi, Omega ) ) # unnormed matrix
    Psi_n = tor.column_stack( ( Psi_n, Omega / n_Omega ) ) # normed matrix
  
  return ( ERR ) # R[2/2]


# ############################################################################ Expansion Order Estimator #############################################################################
def ExpansionOrderEstimator( x, y, MaxLags = ( 15, 15 ), MaxOrder = 5, VarianceAcceptThreshold = 0.98, Plot = True ):
  '''Variable selection function determining the required Monomial expansion order for y and x for rFOrLSR dictionary sparcification.
  This function is NARMAX specific since lagged variables are checked using arbitrary-order polynomial NARX models rather than Taylor expansions.
  
  Note: For model order > 2, this function might be a lot slower than an Arbo with a large dictionary, so use only for analysis or for Dcs not fitting in memory.
  
  ### Inputs:
  -`x`: (1D torch.Tensor) containing the system input vector
  -`y`: (1D torch.Tensor) containing the system output vector
  -`MaxLags`: (2D int Tuple) containing the maximum lags for n_b and n_a, defaults to 30 for both ( n_b, n_a )
  -`MaxOrder`: (int > 0) Maximum approximation order used for the estimation
  -`VarianceAcceptThreshold`: ( float ) the minimum explained variance of the NARMAX expansion to estimate the needed delays
  
  ### Output:
  - `ModelOrder`: (int) The chosen expansion's order, to be passed as (monomial) ExpansionOrder parameter to RegressionMatrix ( Dictionary CTor )
  - `ModelExplainedVariance`: ( (ModelOrder,)-shaped np.array of float) The chosen model's ERR sum (percentage of explained variance)
  '''
  
  # Defensive programming:
  if ( x.shape != y.shape ):                 raise AssertionError( "x and y must have the shape shape.Note that both are flattened for prcessing" )
  if ( ( x.ndim != 1 ) or ( y.ndim != 1 ) ): raise AssertionError( "x or y is not a (p,)-shaped Tensor" )
  if ( ( MaxOrder < 1 ) or ( not isinstance( MaxOrder, int ) ) ): raise AssertionError( "MaxOrder must be an int >= 1" )
  
  y = tor.ravel( y )
  x = tor.ravel( x )

  # ---------------------------------------------------------------------------- A) Model order evaluation ------------------------------------------------------------------------------
  ModelExplainedVariance = [ 0 ] # Summed ERR of all models orders. Start at 0 to represent the 0th order model, being a constant. The optimal constant is the mean of y being 0
  y_cut, RegMat, RegNames = CTors.Lagger( ( x, y ), MaxLags ) # Create the imposed lags
  y_cut -= y_cut.mean()
  ProgressBar = tqdm.tqdm( desc = "Currently analyzed expansion order", unit = "" ) # Initialise progressbar without giving the max to have a counter

  # if less than Minvariance variance is explained, redo the analysis with a higher order model, since maxlag = max variance
  for ModelOrder in range( 1, MaxOrder + 1 ): 
    ProgressBar.update()
    RegMatTMP = CTors.Expander( RegMat, RegNames, ExpansionOrder = ModelOrder )[0] # take only the RegMat and ignore RegNames

    # ComputeERR returns an Array of ERR and stops upon the first ERR > 1 entry and fills the rest of the array with 0, so re-clip the sum since %
    ModelErr = min( 1.0, np.sum( ComputeERR( y_cut, RegMatTMP - RegMatTMP.mean( axis = 0, keepdims = True ) ) ) )
    ModelExplainedVariance.append( ModelErr )
    
    if ( ModelExplainedVariance[-1] >= VarianceAcceptThreshold ): break # do while condition, +1 since next iteration will exceed limit
  
  ProgressBar.close()
  
  if ( ModelExplainedVariance[-1] < VarianceAcceptThreshold ): # loop finished without reaching the threshold
    print( "\nThe VarianceAcceptThreshold was not met, increase MaxOrder and/or MaxLags" )
  else: print( "An order", ModelOrder, "model explaining", 100 * ModelExplainedVariance[-1], "% of the variance was selected.\n" )

  ModelExplainedVariance = np.array( ModelExplainedVariance )

  # --------------------------------------------------------------------------------- B) Plotting ------------------------------------------------------------------------------
  if ( Plot ):
    Fig, Ax = plt.subplots()
    Ax.plot( 100 * ModelExplainedVariance )
    Ax.set_xticks( np.arange( len( ModelExplainedVariance ) ) );
    Ax.set_xticklabels( np.arange( len( ModelExplainedVariance ) ) )
    Ax.grid( which = 'both', alpha = 0.15 )
    Ax.axhline( y = 100 * VarianceAcceptThreshold, c = 'purple', linewidth = 1.5, linestyle = '--' )
    Ax.legend( [ "Model Explained Variance", "User Variance Acceptance Threshold" ] )
    Ax.set( title = f"Model Order Estimation using MaxLags: { MaxLags }", xlabel = "Model Expansion Order", ylabel = "Explained Variance [%]" )
    Fig.tight_layout()

  return ( ModelOrder, ModelExplainedVariance )


# ############################################################################ Variable Selection Procedure #############################################################################
def MaxLagsEstimator( x, y, ModelOrder, MaxLags = ( 15, 15 ), VarianceAcceptThreshold = 0.98, Plot = True, SaveFig = None ):
  '''Variable selection function determining the maximum lags for y and x for rFOrLSR dictionary sparcification.
  This function is NARMAX specific since lagged variables are checked using arbitrary-order polynomial NARX models rather than Taylor expansions.
  Everything in purple on the plot is below the VarianceAcceptThreshold.
  
  Note: For model order > 2, this function might be a lot slower than an Arbo with a large dictionary, so use only for analysis or for Dcs not fitting in memory.
  Note: If any of the recommended lags contain the maximum lag as passed by the user, then the passed lags are not sufficient an a warning will be printed.
  
  ### Inputs:
  -`x`: (1D torch.Tensor) containing the system input vector
  -`y`: (1D torch.Tensor) containing the system output vector
  -`ModelOrder`: (int > 0) Polynomial expansion order used for the estimation
  -`MaxLags`: (2D int Tuple) containing the maximum lags for n_b and n_a (thus x, y), defaults to 15 for both
  -`VarianceAcceptThreshold`: ( float ) the minimum explained variance of the NARMAX expansion to estimate the needed delays
  -`Plot`: (bool) if True, the plot will be generated
  -`SaveFig`: (str) path to save the plot, only works if Plot = True
  
  ### Output:
  - `Grid`: ( MaxLags[0], MaxLags[1] )-shaped np.array containing the ERR values displayed by the plot
  - `Recommendations`: (Dict) containing the optimal lags with the system with the minimal x & y, x, y lags.
  '''
  
  # Defensive programming:
  if ( x.shape != y.shape ):                 raise AssertionError( "x and y must have the shape shape.Note that both are flattened for prcessing" )
  if ( ( x.ndim != 1 ) or ( y.ndim != 1 ) ): raise AssertionError( "x or y is not a (p,)-shaped Tensor" )
  if ( ( ModelOrder < 1 ) or ( not isinstance( ModelOrder, int ) ) ): raise AssertionError( "MaxOrder must be an int >= 1" )
  if ( SaveFig is not None ):
    if ( not Plot ): raise AssertionError( "SaveFig can only be used if Plot = True" )
    SaveFig = SaveFig.replace( "\\", "/" ) # Security
  
  y = tor.ravel( y )
  x = tor.ravel( x )
  
  # --------------------------------------------------------------------------------- A) Model computation ------------------------------------------------------------------------------
  print( f"\nComputing the Grid with maximum lags at ({ MaxLags[0] }, { MaxLags[1] }) and for a model order of { ModelOrder }:" )
  Grid = np.full( ( MaxLags[1] + 1, MaxLags[0] + 1 ), np.nan ) # y's are rows and the x's columns to have a correct graph orientation, +1 due to x[k], y[k]
  ProgressBar = tqdm.tqdm( total = Grid.size ) # Initialise progressbar while declaring total number of iterations

  # Unintuitively, it's the ComputeERR which accounts for 99.99% of the time, not both CTors, so optimizing that out isn't of interest.
  # Also y_cut has a different length at each iteration so it can't be stored
  for na in range( MaxLags[1] + 1 ): # iterate over y lags, +1 to contain the end-of-range value
    for nb in range( MaxLags[0] + 1 ): # iterate over x lags, +1 to contain the end-of-range value
      
      if ( ( Grid[ max( na-1, 0 ), nb] == 1.0 ) and ( Grid[ na, max( nb-1, 0 )] == 1.0 ) ): 
        Grid[ na, nb ] = 1.0 # if both previous regressor lists are already sufficient to achive full precision, don't recompute unnecessarily everything
      
      else:
        y_cut, RegMat, RegNames = CTors.Lagger( Data = ( x, y ), Lags = ( nb, na ) ) # construct linear regressor matrix, ignore RegNames return
        RegMat, RegNames = CTors.Expander( RegMat, RegNames, ExpansionOrder = ModelOrder )
        
        ERRArray = ComputeERR( y_cut - y_cut.mean(), RegMat - RegMat.mean( axis = 0, keepdims = True ) ) # Returns an Array of ERR (clipped to 1)
        Grid[na, nb] = min( 1.0, np.sum( ERRArray ) ) # ComputeERR stops upon the first ERR > 1 entry and fills the rest of the array with 1, so re-clip the sum

      ProgressBar.update() # increase count
  ProgressBar.close() # Necessary
  
  # --------------------------------------------------------------------------------- B) Lags recommendation -----------------------------------------------------------------------------------
  Recommendations = { "Min_XY": ( MaxLags[0], MaxLags[1] ), # Position with the smallest x and y lags
                      "Min_X":  ( MaxLags[0], MaxLags[1] ), # Position with the smallest x lag
                      "Min_Y":  ( MaxLags[0], MaxLags[1] ), # Position with the smallest y lag
                    }
  
  BestIdx = np.inf

  for na in range( MaxLags[1] + 1 ): # over y-lags
    for nb in range( MaxLags[0] + 1 ): # over x-lags
      if ( Grid[ na, nb ] > VarianceAcceptThreshold ): # valid solution
        if ( na + nb < BestIdx ): # Smallest a+b position. Taking <= would allow more y terms in, yielding less numereically stable solution systems
          BestIdx = na + nb
          Recommendations["Min_XY"] = ( nb, na ) # x-lags then y-lags

  for na in range( MaxLags[1] + 1 ): # iterate over y values (rows), since we're looking for the smallest nb with the smallest na
    BestIdx = np.argmax( Grid[ na, : ] > VarianceAcceptThreshold ) # find first nb > VarianceAcceptThreshold.
    if ( BestIdx != 0 ): Recommendations["Min_Y"] = ( BestIdx, na ); break

  for nb in range( MaxLags[0] + 1 ): # iterate over x values (columns), since we're looking for the smallest na with the smallest nb
    BestIdx = np.argmax( Grid[ : , nb ] > VarianceAcceptThreshold ) # find the first na > VarianceAcceptThreshold.
    if ( BestIdx != 0 ): Recommendations["Min_X"] = ( nb, BestIdx ); break


  if ( np.max( Grid ) < VarianceAcceptThreshold ): print( "\nWARNING: The passed MaxLags don't suffise for the desired variance\n" )
  # ---------------------------------------------------------------------------------- C) Plot ---------------------------------------------------------------------------------------
  if ( Plot ): # An 0.5 offset is added everywhere to have the labels and the dots in the middle of each square rather than left + below it.)
    ColorBarMax = np.max( Grid )
    if ( ColorBarMax <= VarianceAcceptThreshold ): ColorBarMax = 1 # if the variance isn't reached set the max to make everything purple (minimum)

    Fig, Ax = plt.subplots() # force new figure
    Im = Ax.pcolormesh( Grid, cmap = 'viridis', edgecolors = 'k', linewidth = 2,
                        vmin = VarianceAcceptThreshold, vmax = ColorBarMax, # Everything below the VarianceAcceptThreshold is not of interest → color clip.
                      )

    DotSize = 60
    Ax.scatter( Recommendations["Min_Y"][0] + 0.5,  Recommendations["Min_Y"][1] + 0.5,  color = 'r', s = DotSize ) # red
    Ax.scatter( Recommendations["Min_X"][0] + 0.5,  Recommendations["Min_X"][1] + 0.5,  color = 'r', s = DotSize ) # blue
    Ax.scatter( Recommendations["Min_XY"][0] + 0.5, Recommendations["Min_XY"][1] + 0.5, color = 'r', s = DotSize ) # black, last to be on top if multiple at same spot

    Ax.set( title = f"Model Order: { ModelOrder }",
            xlabel = "x[k-i] regressors",                    ylabel = "y[k-i] regressors",
            xlim = ( 0, MaxLags[0] + 1 ),                    ylim = ( 0, MaxLags[1] + 1 ), # Start at 0 in the bottom left corner (flips y-axis compared to usual pclormesh)
            xticks = ( 0.5 + np.arange( MaxLags[0] + 1 ) ),  yticks = ( 0.5 + np.arange( MaxLags[1] + 1 ) ), # Move to middle
            xticklabels =  ( np.arange( MaxLags[0] + 1 ) ),  yticklabels =  ( np.arange( MaxLags[1] + 1 ) ), # Compensate
            aspect = 'equal'
          )
    
    Fig.colorbar( Im ) # defaults to curernt Figure
    Fig.tight_layout()

    if ( SaveFig is not None ): plt.savefig( SaveFig )
  
  
  return ( Recommendations, Grid )