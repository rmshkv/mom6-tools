#!/usr/bin/env python

import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
from mom6_tools.DiagsCase import DiagsCase
from mom6_tools.ClimoGenerator import ClimoGenerator
from collections import OrderedDict
import yaml, os

try: import argparse
except: raise Exception('This version of python is not new enough. python 2.7 or newer is required.')

def options():
  parser = argparse.ArgumentParser(description='''Script for plotting time-series of transports across vertical sections.''')
  parser.add_argument('diag_config_yml_path', type=str, help='''Full path to the yaml file  \
    describing the run and diagnostics to be performed.''')
  parser.add_argument('-l','--label',    type=str, default='', help='''Label to add to the plot.''')
  parser.add_argument('-n','--case_name', type=str, default='test', help='''Case name (default=test)''')
  parser.add_argument('-o','--outdir',   type=str, default='.', help='''Directory in which to place plots.''')
  parser.add_argument('-ys','--year_start',      type=int, default=0,  help='''Start year to plot (default=0)''')
  parser.add_argument('-ye','--year_end',      type=int, default=1000, help='''Final year to plot (default=1000)''')
  parser.add_argument('-debug', help='''Add priting statements for debugging purposes''', action="store_true")
  cmdLineArgs = parser.parse_args()
  return cmdLineArgs

def HorizontalMeanRmse_da(var, dims=('yh', 'xh'), weights=None, basins=None, debug=False):
  """
  weighted horizontal root-mean-square error for DataArrays

  Parameters
  ----------

  var : xarray.DataArray
    Difference between the actual values and predicted values (model - obs, or residual).

  dims : tuple, str
    Dimensions over which to apply average. Default is ('yh', 'xh').

  weights : xarray.DataArray, optional
      weights to apply. It can be a masked array.

  basins : xarray.DataArray, optional
      Basins mask to apply. If True, returns horizontal mean RMSE for each basin provided. \
      Basins must be generated by genBasinMasks. Default is False.

  debug : boolean, optional
    If true, print stuff for debugging. Default is False.

  Returns
  -------
  reduced : DataArray
      New xarray.DataArray with horizontal mean RMSE.
  """

  if dims[0] not in var.dims:
    raise ValueError("weights does not have dimensions given by dims[0]")
  if dims[1] not in var.dims:
    raise ValueError("weights does not have dimensions given by dims[1]")

  if basins is not None and weights is None:
    raise ValueError("Basin masks can only be applied if weights are provided.")

  if weights is None:
    return np.sqrt((var**2).mean(dim=dims))
  else:
    if basins is None:
      # global reduction
      if not isinstance(weights, xr.DataArray):
        raise ValueError("weights must be a DataArray")
      if dims[0] not in weights.dims:
        raise ValueError("weights does not have dimensions given by dims[0]")
      if dims[1] not in weights.dims:
        raise ValueError("weights does not have dimensions given by dims[1]")

      total_weights = weights.sum(dim=dims)
      if debug: print('total weights is:', total_weights.values)
      out = np.sqrt((var**2 * weights).sum(dim=dims) / total_weights)
      if debug: print('rmse is:', out.values)

    else:
      # regional reduction
      if 'region' not in basins.coords:
        raise ValueError("Regions does not have coordinate region. Please use genBasinMasks \
                          to construct the basins mask.")
      if len(weights.shape)!=3:
        raise ValueError("If basins is provided, weights must be a 3D array.")

      rmask_od = OrderedDict()
      for reg in basins.region:
        if debug: print('Region: ', reg)
        # construct a 3D region array
        tmp = np.repeat(basins.sel(region=reg).values[np.newaxis, :, :], len(var.z_l), axis=0)
        region3d = xr.DataArray(tmp,dims=var.dims[1::],
                                coords= {var.dims[1]: var.z_l,
                                         var.dims[2]: var.yh,
                                         var.dims[3]: var.xh})
        # select weights to where region3d is one
        tmp_weights = weights.where(region3d == 1.0)
        total_weights = tmp_weights.sum(dim=dims)
        rmask_od[str(reg.values)] = np.sqrt((var**2 * tmp_weights).sum(dim=dims) / total_weights)

        if debug: print('total weights is:', total_weights.values)

      out = xr.DataArray(np.zeros((len(basins.region), var.shape[0], var.shape[1])),
                         dims=(basins.dims[0], var.dims[0], var.dims[1]),
                         coords={basins.dims[0]:list(rmask_od.keys()),
                                 var.dims[0]: var.time,
                                 var.dims[1]: var.z_l})

      for i, rmask_field in enumerate(rmask_od.values()):
        out.values[i,:,:] = rmask_field

    return out

def HorizontalMeanDiff_da(var, dims=('yh', 'xh'), weights=None, basins=None, debug=False):
  """
  weighted horizontal mean difference (model - obs) for DataArrays

  Parameters
  ----------

  var : xarray.DataArray
    Difference between the actual values and predicted values (model - obs, or residual).

  dims : tuple, str
    Dimension(s) over which to apply average. Default is ('yh', 'xh').

  weights : xarray.DataArray
      weights to apply. It can be a masked array.

  basins : xarray.DataArray, optional
      Basins mask to apply. If True, returns horizontal mean difference for each basin provided. \
      Basins must be generated by genBasinMasks. Default is False.

  debug : boolean, optional
    If true, print stuff for debugging. Default False

  Returns
  -------
  reduced : DataArray
      New xarray.DataArray with horizontal mean difference.
  """

  if dims[0] not in var.dims:
    raise ValueError("weights does not have dimensions given by dims[0]")
  if dims[1] not in var.dims:
    raise ValueError("weights does not have dimensions given by dims[1]")

  if basins is not None and weights is None:
    raise ValueError("Basin masks can only be applied if weights are provided.")
  if weights is None:
    return var.mean(dim=dims)
  else:
    if basins is None:
      # global reduction
      if not isinstance(weights, xr.DataArray):
        raise ValueError("weights must be a DataArray")
      if dims[0] not in weights.dims:
        raise ValueError("weights does not have dimensions given by dims[0]")
      if dims[1] not in weights.dims:
        raise ValueError("weights does not have dimensions given by dims[1]")

      total_weights = weights.sum(dim=dims)
      if debug: print('total weights is:', total_weights.values)
      out = (var * weights).sum(dim=dims) / total_weights
      if debug: print('horizontal mean is:', out.values)
    else:
      # regional reduction
      if 'region' not in basins.coords:
        raise ValueError("Regions does not have coordinate region. Please use genBasinMasks \
                          to construct the basins mask.")
      if len(weights.shape)!=3:
        raise ValueError("If basins is provided, weights must be a 3D array.")

      rmask_od = OrderedDict()
      for reg in basins.region:
        if debug: print('Region: ', reg)
        # construct a 3D region array
        tmp = np.repeat(basins.sel(region=reg).values[np.newaxis, :, :], len(var.z_l), axis=0)
        region3d = xr.DataArray(tmp,dims=var.dims[1::],
                                coords= {var.dims[1]: var.z_l,
                                         var.dims[2]: var.yh,
                                         var.dims[3]: var.xh})
        # select weights to where region3d is one
        tmp_weights = weights.where(region3d == 1.0)
        total_weights = tmp_weights.sum(dim=dims)
        rmask_od[str(reg.values)] = (var * tmp_weights).sum(dim=dims) / total_weights


      out = xr.DataArray(np.zeros((len(basins.region), var.shape[0], var.shape[1])),
                         dims=(basins.dims[0], var.dims[0], var.dims[1]),
                         coords={basins.dims[0]:list(rmask_od.keys()),
                                 var.dims[0]: var.time,
                                 var.dims[1]: var.z_l})

      for i, rmask_field in enumerate(rmask_od.values()):
        out.values[i,:,:] = rmask_field

    return out

def plotPanel(section,n,observedFlows=None,colorCode=True):
    ax = plt.subplot(6,3,n+1)
    color = '#c3c3c3'; obsLabel = None
    if section.label in observedFlows.keys():
      if isinstance(observedFlows[section.label],tuple):
        if colorCode == True:
          if min(observedFlows[section.label]) <= section.data.mean() <= max(observedFlows[section.label]):
            color = '#90ee90'
          else: color = '#f26161'
        obsLabel = str(min(observedFlows[section.label])) + ' to ' + str(max(observedFlows[section.label]))
      else: obsLabel = str(observedFlows[section.label])
    plt.plot(section.time,section.data,color=color)
    plt.title(section.label,fontsize=12)
    plt.text(0.04,0.11,'Mean = '+'{0:.2f}'.format(section.data.mean()),transform=ax.transAxes,fontsize=10)
    if obsLabel is not None: plt.text(0.04,0.04,'Obs. = '+obsLabel,transform=ax.transAxes,fontsize=10)
    if section.ylim is not None: plt.ylim(section.ylim)
    if n in [1,4,7,10,13,16]: plt.ylabel('Transport (Sv)')

def main(stream=False):

  # Get options
  cmdLineArgs = options()

  # Read in the yaml file
  diag_config_yml = yaml.load(open(cmdLineArgs.diag_config_yml_path,'r'), Loader=yaml.Loader)

  # Create the case instance
  dcase = DiagsCase(diag_config_yml['Case'], xrformat=True)

  # Load the grid
  grd = dcase.grid

  # Create the climatology instance
  climo = ClimoGenerator(diag_config_yml['Climo'], dcase)

  # Compute the climatology dataset
  dset_climo = climo.stage()

  # load PHC2 data
  phc_path = '/glade/p/cesm/omwg/obs_data/phc/'
  phc_temp = xr.open_mfdataset(phc_path+'PHC2_TEMP_tx0.66v1_34lev_ann_avg.nc', decode_times=False)
  phc_salt = xr.open_mfdataset(phc_path+'PHC2_SALT_tx0.66v1_34lev_ann_avg.nc', decode_times=False)

  # get theta and salt and rename coordinates to be the same as the model's
  thetao_obs = phc_temp.TEMP.rename({'X': 'xh','Y': 'yh', 'depth': 'z_l'});
  salt_obs = phc_salt.SALT.rename({'X': 'xh','Y': 'yh', 'depth': 'z_l'});
  # set coordinates to the same as the model's
  thetao_obs['xh'] = thetao_model.xh; thetao_obs['yh'] = thetao_model.yh;
  salt_obs['xh'] = salt_model.xh; salt_obs['yh'] = salt_model.yh;

  # leaving this here to catch if start/end years outside the range of the dataset
  res = Transport(cmdLineArgs,'Agulhas_Section','umo',label='Agulhas',ylim=(100,200))

  try: res = Transport(cmdLineArgs,'Agulhas_Section','umo',label='Agulhas',ylim=(100,250)); plotSections.append(res)
  except: print('WARNING: unable to process Agulhas_section')

if __name__ == '__main__':
  main()
