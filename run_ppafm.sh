#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

DFT_DIR="parent_calc_folder"
HARTREE="$DFT_DIR/aiida-HART-v_hartree-1_0.cube"

NX=$(sed '4q;d' $HARTREE | awk '{print $1;}')
NY=$(sed '5q;d' $HARTREE | awk '{print $1;}')
NZ=$(sed '6q;d' $HARTREE | awk '{print $1;}')

echo "gridN $NX $NY $NZ" >> params.ini

ppafm-generate-ljff -i geom.xyz -f npy
ppafm-generate-elff -i $HARTREE -f npy
ppafm-relaxed-scan -f npy --disp --pos
ppafm-plot-results --df --cbar --save_df -f npy
