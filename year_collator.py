#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iFEED Data consolidation tool Level 1

Name: year_collator.py

Usage: python year_collator.py -d <dir> -o <out> -p <proc>

Description:
    Combine all data for a each year in the iFEED project. This data is comprised of
    120 files per year (10 production levels, 10 irrigation levels).
    Data is combined from all 120 individual ascii files (with 49 columns per file and each
    row relating to a single 0.5degx0.5deg gridcell) into a set of 100 NetCDF files using
    iris cubes. Program is set up to use multiprocessing also as the data combination
    process can be time consuming. Data is then be combined using nco.

Arguments:
    dir   : Location of the folder containing the yearly raw GLAM outputs. This should
            be a directory and contain a set of 120 folders with years from 1980 to 2099.
            The contents of the folder are checked to ensure all years are present.
            The folder itself should have the hierarchy country/crop/model/rcp/years;
            since this hierarchy is determined by outside scripts, it's validity is
            assumed and not checked. Default is the location of this python script
    out   : The directory of the output netCDF file. Default is the location of this python
            script. The output filename is autogenerated from the directory structure as
            $out/ind_rcp/$country/$crop_$model_$rcp.nc.
    proc  : Number of parallel processes (maximum 40). Default is 1

Restrictions:
    There should be a set of 120 folders with years from 1980 to 2099 in execution folder
    Assumption that folder structure is country/crop/model/rcp/years, and that filenaming
    convention is:

        <crop>_<country>_amma_<model>_<rcp>_Fut_<year>_<prod>_<irr>_1.out

    This filenaming convention can be changed on lines 446-447

Created June 2020

@author: Christopher Symonds, CEMAC, University of Leeds
"""

import iris
import numpy as np
import pandas as pd
import os
import argparse
import time
from multiprocessing import Pool
import errlib
from nco import Nco

countries={
        "malawi":0,
        "safrica":1,
        "tanzania":2,
        "zambia":3
        }
crops={
      "cassava":0,
      "groundnut":1,
      "maize":2,
      "millet":3,
      "potato":4,
      "rice":5,
      "sorghum":6,
      "soybean":7,
      "sugarcane":8,
      "sweetpot":9,
      "wheat":10
      }
models={
       "bcc-csm1-1":0,
       "bcc-csm1-1-m":1,
       "BNU-ESM":2,
       "CanESM2":3,
       "CNRM-CM5":4,
       "CSIRO-Mk3-6-0":5,
       "GFDL-CM3":6,
       "GFDL-ESM2G":7,
       "GFDL-ESM2M":8,
       "IPSL-CM5A-LR":9,
       "IPSL-CM5A-MR":10,
       "MIROC5":11,
       "MIROC-ESM":12,
       "MIROC-ESM-CHEM":13,
       "MPI-ESM-LR":14,
       "MPI-ESM-MR":15,
       "MRI-CGCM3":16,
       "NorESM1-M":17
       }
rcps={
     "rcp26":0,
     "rcp85":2
     }

prod_lst=["0.1","0.2","0.3","0.4","0.5","0.6","0.7","0.8","0.9","1"]
irr_lst=["0","0.1","0.2","0.3","0.4","0.5","0.6","0.7","0.8","0.9","1","2"]

column={'V1': 'Year',
        'V2': 'Latitude',
        'V3': 'Longitude',
        'V4': 'Planting date',
        'V5': 'Final crop stage (ISTG)',
        'V6': 'Mean root length density by volume',
        'V7': 'LAI (specifically RLAI (2))',
        'V8': 'Yield',
        'V9': 'Biomass',
        'V10': 'Empty (irrigated fraction; SLA)',
        'V11': 'Harvest index',
        'V12': 'Cumulative rain',
        'V13': 'Solar radiation',
        'V14': 'Total soil water',
        'V15': 'Transpiration',
        'V16': 'Evapotranspiration_1',
        'V17': 'Potential evapotranspiration (limited by soil transport, LAI and energy)',
        'V18': 'Soil water stress factor',
        'V19': 'Evapotranspiration_2',
        'V20': 'Runoff',
        'V21': 'Cumulative runoff',
        'V22': 'Potential (root-limited) uptake',
        'V23': 'Cumulative potential uptake',
        'V24': 'Drainage',
        'V25': 'Cumulative drainage',
        'V26': 'Potential (energy-limited) transpiration',
        'V27': 'Cumulative potential transpiration',
        'V28': 'Cumulative evaporation',
        'V29': 'Max LAI during growing season',
        'V30': 'Cumulative potential evaporation',
        'V31': 'Cumulative transpiration',
        'V32': 'Root length density by area',
        'V33': 'Root Length Density by Area / LAI',
        'V34': 'Rainfall',
        'V35': 'Change in soil moisture',
        'V36': 'Absorbed radiation',
        'V37': 'Duration',
        'V38': 'Mean vapour pressure deficit',
        'V39': 'Tot net radiation',
        'V40': 'Total percentage of pods setting (TOTPP)',
        'V41': 'Total percentage of pods setting considering temperature only (TOTPP_HIT)',
        'V42': 'Total percentage of pods setting considering water stress only (TOTPP_WAT)',
        'V43': 'Mean temperature during the crop season (planting to harvest).',
        'V44': 'Factor DHDT is reduced by due to heat stress when HTS=1 or 2 (HT_FAC)',
        'V45': 'TOTWHARVDEP',
        'V46': 'STORED_WATER',
        'V47': 'Panicle initiation date (DOY - Sorghum only)',
        'V48': 'Flowering date (DOY - Sorghum only)',
        'V49': 'Total supplementary irrigation added to VOLSW (1) if using SUP irrigation'
        }
var_nm={'V1' : 'year',
        'V2' : 'latitude',
        'V3' : 'longitude',
        'V4' : 'plant_date',
        'V5' : 'istg_final',
        'V6' : 'rlv_mean',
        'V7' : 'rlai_2',
        'V8' : 'yield',
        'V9' : 'biomass',
        'V10': 'sla',
        'V11': 'harv_index',
        'V12': 'tot_rain',
        'V13': 'srad_final',
        'V14': 'soil_wat',
        'V15': 'trans',
        'V16': 'evtrans1',
        'V17': 'pot_evtrans',
        'V18': 'soil_wat_fac',
        'V19': 'evtrans2',
        'V20': 'runoff',
        'V21': 'tot_runoff',
        'V22': 'pot_uptake',
        'V23': 'tot_pot_uptake',
        'V24': 'drainage',
        'V25': 'tot_drainage',
        'V26': 'pot_trans',
        'V27': 'tot_pot_trans',
        'V28': 'tot_evap',
        'V29': 'lai_max',
        'V30': 'tot_pot_ev',
        'V31': 'tot_trans',
        'V32': 'rla',
        'V33': 'rla_over_lai',
        'V34': 'rain_final',
        'V35': 'd_soil_moist',
        'V36': 't_rad_abs',
        'V37': 'dur',
        'V38': 'mean_vap_pres_def',
        'V39': 'Tot_net_rad',
        'V40': 'tot_per_pod',
        'V41': 'tot_per_pod_hit',
        'V42': 'tot_per_pod_wat',
        'V43': 'mean_temp',
        'V44': 'dhdt_fac',
        'V45': 'totwharvdep',
        'V46': 'stor_wat',
        'V47': 'pan_init_date',
        'V48': 'flowr_date',
        'V49': 'tot_irr_sup'
        }
var_units={'V1' : 'year',
           'V2' : 'degrees_north',
           'V3' : 'degrees_east',
           'V4' : 'days',
           'V5' : '1',
           'V6' : 'cm/cm^3',
           'V7' : 'm^2/m^2',
           'V8' : 'kg/ha',
           'V9' : 'kg/ha',
           'V10': '1',
           'V11': '1',
           'V12': 'cm',
           'V13': 'MJ/m^2',
           'V14': 'cm',
           'V15': 'cm',
           'V16': 'cm',
           'V17': 'cm',
           'V18': '1',
           'V19': 'cm',
           'V20': 'cm',
           'V21': 'cm',
           'V22': 'cm',
           'V23': 'cm',
           'V24': 'cm',
           'V25': 'cm',
           'V26': 'cm',
           'V27': 'cm',
           'V28': 'cm',
           'V29': 'm^2/m^2',
           'V30': 'cm',
           'V31': 'cm',
           'V32': 'cm/cm^2',
           'V33': 'cm/cm^2',
           'V34': 'cm',
           'V35': 'cm',
           'V36': 'MJ/m^2',
           'V37': 'days',
           'V38': 'kPa',
           'V39': 'MJ/m^2',
           'V40': '%',
           'V41': '%',
           'V42': '%',
           'V43': 'celsius',
           'V44': '1',
           'V45': 'cm',
           'V46': 'cm',
           'V47': 'day',
           'V48': 'day',
           'V49': 'cm'
           }

nco=Nco()

def nextPath(path_pattern):
    """
    Finds the next free path in an sequentially named list of files

    e.g. path_pattern = 'file-%s.txt':

    file-1.txt
    file-2.txt
    file-3.txt

    Runs in log(n) time where n is the number of existing files in sequence
    """
    i = 1

    # First do an exponential search
    while os.path.exists(path_pattern % i):
        i = i * 2

    # Result lies somewhere in the interval (i/2..i]
    # We call this interval (a..b] and narrow it down until a + 1 = b
    a, b = (i // 2, i)
    while a + 1 < b:
        c = (a + b) // 2 # interval midpoint
        a, b = (c, b) if os.path.exists(path_pattern % c) else (a, c)

    return path_pattern % b


def readargs():
    '''
    Read input arguments if run as separate program
    '''

    parser = argparse.ArgumentParser(description=(
        'Combine the raw data ouytputs for a particular climate scheme into'
        ' a single NetCDF file.'
        ))

    parser.add_argument('--dir', '-d',
                        type=str,
                        help='Path to directory for climate scheme',
                        default='.')

    parser.add_argument('--out', '-o',
                        type=str,
                        help='Directory for output file',
                        default='.')

    parser.add_argument('--proc', '-p',
                        type=int,
                        help='Number of parallel processes used for data reading and combination',
                        default=1)

    args = parser.parse_args()

    if not isinstance(args.dir,str):
        raise errlib.ArgumentsError("Data running directory is not a string!\n")

    if not isinstance(args.out,str):
        raise errlib.ArgumentsError("Output filename is not a string!\n")

    if not isinstance(args.proc,int):
        raise errlib.ArgumentsError("Number of parallel processes is not an integer!\n")

    if args.dir=='.':
        ascdir=os.getcwd()
    else:
        ascdir=args.dir

    if ascdir[-1]=="/":
        simval=ascdir.split('/')[-5:-1]
    else:
        simval=ascdir.split('/')[-4:]
        ascdir=ascdir+"/"

    if not os.path.exists(ascdir):
        raise errlib.ArgumentsError('Path to data files does not exist: '
                             + ascdir+'\n')

    contents=[i for i in os.listdir(ascdir) if os.path.isdir(os.path.join(ascdir,i))]

    years = [str(i) for i in range(1980,2100)]
    if not all(x in contents for x in years):
        raise errlib.ArgumentsError('Data file directory expected to contain 120 numbered folders\n'+
                             'numbered from 1980 to 2099 inclusive, but these folders were\n'+
                             'not found. Check that the directory argument is correct.\n'+
                             'Directory checked was '+ascdir+'\n')

    if not os.path.exists(args.out):
        raise errlib.ArgumentsError('Directory to write netCDF file to'
                                    + ' does not exist\n')

    if args.out and not os.path.isdir(args.out):
        raise errlib.ArgumentsError('Directory to write netCDF file to'
                                    + ' does not exist\n')

    try:
        os.makedirs(os.path.join(args.out,"ind_rcp",simval[0]))
    except FileExistsError:
        # directory already exists
        pass

    outfil=os.path.join(args.out,"ind_rcp",simval[0],"_".join(simval[1:]))

    if args.proc > 40:
        raise errlib.ArgumentsError("Too many processes requested. Maximum of 40\n")

    procs=args.proc

    retdata=[ascdir,simval,procs,outfil]

    return retdata


def getyrs(locdir):

    yrs=[]
    for fol in os.walk(locdir):
        if len(fol[2]) >= 120:
            yr=fol[0].split('/')[-1]
            if not yr=='':
                yrs.append(yr)

    return yrs


def readascii(path,dimvals):

    try:
        df = pd.read_csv(path, sep=' ')
    except:
        raise errlib.FileError("Error reading file at "+path+"\n")

    filenm = os.path.split(path)[1]

    n=df['V2'].max()
    s=df['V2'].min()
    e=df['V3'].max()
    w=df['V3'].min()

    if all(x == df['V1'][1] for x in df['V1']):
        time = iris.coords.DimCoord(df['V1'][1],standard_name="time",long_name="Time",var_name="time",units="year")
    else:
        print ("Error in data file "+filenm+".\n")
        print ("Multiple years read within same file")

    prodlev = iris.coords.DimCoord(float(filenm.split('_')[-3]),long_name="production level",var_name="prod_lev",units=1)
    irr_lev = iris.coords.DimCoord(float(filenm.split('_')[-2]),long_name="irrigation level",var_name="irr_lev",units=1)
    #country_dim = iris.coords.DimCoord(float(dimvals[0]),long_name="country",var_name="country",units=1)
    crop_dim = iris.coords.DimCoord(float(dimvals[1]),long_name="crop",var_name="crop",units=1)
    model_dim = iris.coords.DimCoord(float(dimvals[2]),long_name="climate model",var_name="model",units=1)
    rcp_dim = iris.coords.DimCoord(float(dimvals[3]),long_name="rep. conc. pathway",var_name="rcp",units=1)

    grid=np.zeros((1,int(((n-s)*2)+1),int(((e-w)*2)+1),1,1,1,1,1))
    grid.fill(-99)

    latitude  = iris.coords.DimCoord(np.linspace(s, n, int((n-s)*2)+1), standard_name='latitude',  units='degrees_north', long_name='Latitude',  var_name='lat')
    longitude = iris.coords.DimCoord(np.linspace(w, e, int((e-w)*2)+1), standard_name='longitude', units='degrees_east', long_name='Longitude', var_name='lon')

    cube_templ=iris.cube.Cube(grid, dim_coords_and_dims=[(time,0),(latitude,1),(longitude,2),(prodlev,3),(irr_lev,4),(rcp_dim,5),(model_dim,6),(crop_dim,7)])

    cubelist=iris.cube.CubeList([])
    for col in df:
        num=int(col[1:])
        if num > 3:
            cube_layer=cube_templ.copy()
            for index, row in df.iterrows():
                lat=row['V2']
                lon=row['V3']
                a=np.where(cube_layer.coord('latitude').points==float(lat))
                b=np.where(cube_layer.coord('longitude').points==float(lon))
                cube_layer.data[0,a[0][0],b[0][0],0,0,0,0,0]=row[col]

            cube_layer.data=np.ma.masked_equal(cube_layer.data,-99.)
            cube_layer.long_name=column[col]
            cube_layer.units=var_units[col]
            cube_layer.rename(var_nm[col])
            cube_layer.data.fill_value=-99.0

            cubelist.append(cube_layer)

    return cubelist

def fullyr(data):

    valnames=data[1][0]
    ascdir = data[1][1]
    dimvals = data[1][2]
    outfil=data[1][3]
    yr=data[0]

    cubelst=iris.cube.CubeList([])

    tot=len(prod_lst)*len(irr_lst)
    n=0
    for prod in prod_lst:
        for irr in irr_lst:
            n+=1
            filenm=valnames[1]+"_"+valnames[0]+"_amma_"+valnames[2]+"_"
            filenm=filenm+valnames[3]+"_Fut_"+yr+"_"+prod+"_"+irr+"_1.out"
            path=ascdir+yr+"/"+filenm

            cubelst+=readascii(path, dimvals)
            print ("cube {} of {} appended for year {}".format(n,tot,yr))

    outnm="{}_{}.nc".format(outfil,data[0])
    outcube(cubelst.concatenate(), outnm)

    return outnm

def multiprocess_rcp (indata):

    [yrs,ascdir,valnames,procs,dimvals,outfil]=indata

    yearlist=[]

    locproc=min(len(yrs),procs)

    args=[valnames,ascdir,dimvals,outfil]

    itterable = [[yr, args] for yr in yrs]

    list_of_chunks=np.array_split(itterable,len(itterable)/locproc)

    start=time.time()

    with Pool(processes=locproc) as pool:

        for chunk in list_of_chunks:
            yearlist+=pool.map(fullyr,chunk)

    yearlist.sort()

    catdata(yearlist,outfil)

    end=time.time()

    print ('time to combine ascii to a single nc:',int(end-start))

def singleprocess_rcp (indata):

    [yrs,ascdir,valnames,procs,dimvals,outfil]=indata

    start=time.time()

    args=[valnames,ascdir,dimvals,outfil]

    itterable = [[yr, args] for yr in yrs]

    yearlist=[]

    for data in itterable:
        yearlist.append(fullyr(data))

    yearlist.sort()

    catdata(yearlist,outfil)

    end=time.time()

    print ('time to combine ascii to a set of nc files:',int(end-start))

def outcube(cube, fname):

    if (os.path.exists(fname)):
        outfile=nextPath(fname[:-3]+'_%s.nc')
    else:
        outfile=fname

    iris.fileformats.netcdf.save(cube, outfile, zlib=True)

def catdata(catlist,outfil):

    nco.ncks(input=catlist[0], output="{}_recdim.nc".format(catlist[0][:-3]), options=['-O','-h', '--mk_rec_dmn time'])
    catlist.insert(1,"{}_recdim.nc".format(catlist[0][:-3]))
    newfile=outfil+'.nc'
    (path, file) = os.path.split(newfile)
    if not os.path.exists(path):
        os.makedirs(path)
    nco.ncrcat(input=catlist[1:], output=newfile)

    for file in catlist:
        os.remove(file)

def main():

    [ascdir,valnames,NBR_PROCESSES,outfil]=readargs()

    yrs=getyrs(ascdir)

    try:
        dimvals=[countries[valnames[0]],crops[valnames[1]],models[valnames[2]],rcps[valnames[3]]]
    except:
        raise errlib.ArgumentsError("Could not assign dimensions based on the values: \n\ncountry = {},\ncrop = {},\nmodel = {},\nrcp = {}".format(*valnames))

    indata=[yrs,ascdir,valnames,NBR_PROCESSES,dimvals,outfil]

    if NBR_PROCESSES>1:

        multiprocess_rcp(indata)

    else:

        singleprocess_rcp(indata)


if __name__=="__main__":
    main()