#!/usr/bin/env python3

# Copyright (c)2023. IonQ, Inc. All rights reserved.
#
# Preprocessor to decompose multi-control gates.
#
# It takes 1-3 arguments:
#     - The input file name.
#     - Optional: the output file name. If none is provided it uses the input
#       file name with "_preprocessed" as the output file name.
#     - Optional, only allowed if the output file name is specified too: the
#       maximum number of qbits.

import copy
import math
import os
import sys

pi = 4.0 * math.atan(1.0)

nq = 0

# maximum number of quantum bits.
max_nq = 100

num_cont_thres = 7    # based on what can be done efficiently.

# :: 32 - 7 >> 1, meaning I use as many dirty ancillas (~3) as possible.
# :: when this is no longer the case, we will revisit this problem.

diff_thres = 1.0e-13  # Some arbitrary precision limit.

depth = 0
debug = 0
stat = 0
nsamp = 0

# Lists that represent the input instructions.
igate_type  = []     # list[int]
ioperand = []        # list[list[int]]
ang_rot  = []        # list[float]

current_output = None

def main(argv):
    global max_nq
    if len(argv) < 2 or len(argv) > 4:
        print("usage: {} input.txt [output.txt [max number of qbits]]".format(argv[0]))
        print("- outputs to input.txt_preprocessed by default")
        print("- program stats sent to stderr")
        sys.exit(-1)

    fname = argv[1].strip()
    if len(argv) < 3:
        fnameout = fname.strip() + '_preprocessed'
    else:
        fnameout = argv[2]

    if len(argv) < 4:
        max_nq = 100   # currently arbitrarily chosen ...
    else:
        max_nq = int(argv[3])

    src_file = open(fname, 'r')
    dest_tmp_file_name = fnameout + '_temp'
    dest_tmp_file = open(dest_tmp_file_name, 'w')
    global current_output
    current_output = dest_tmp_file

    prelim(src_file) # set nq, depth, and debug

    igate_type = [0] * depth
    ang_rot = [0.0] * depth

    ioperand = []
    for j in range(depth):
        inner = [0] * max_nq
        ioperand.append(inner)

    read(src_file, igate_type, ang_rot, ioperand)
    src_file.close()

    itof_count = 0
    convert(igate_type ,ang_rot, ioperand)
    dest_tmp_file.close()

    dest_temp_file = open(dest_tmp_file_name)
    nops = 0; max_q = 0
    for line in dest_temp_file:
        if (line[0:2] != 'op'):
            continue

        nops += 1
        line_length = len(line)
        current_pos = 2
        while (current_pos < line_length):
            if (line[current_pos] == '['):
                current_pos += 1
                left = current_pos
                while (current_pos < line_length):
                    c = line[current_pos]
                    current_pos += 1
                    if (c == ']' or c == ','):
                        iq = int(line[left : current_pos - 1])
                        max_q = max(max_q, iq)
                        if (c == ']'):
                            break
            else:
                current_pos += 1

    dest_file = open(fnameout, 'w')
    dest_file.write('// max qubit {}\n'.format(max_q + 1))
    dest_file.write('// ops count {}\n'.format(nops))
    dest_file.write('// tof count {}\n'.format(itof_count))
    if (debug):
        dest_file.write('// debug\n')

    if (nsamp > 0):
        dest_file.write('// shots {}\n'.format(nsamp))

    dest_temp_file.seek(0)
    for line in dest_temp_file:
        dest_file.write(line)

    dest_tmp_file.close()
    os.remove(dest_tmp_file_name)
    dest_file.close()
    return 0

#================
# Extracts nq == # of qubits in a given quantum circuit
#          depth == # of stages of (parallel) gates in the circuit
#          debug == is debug flag requested
#------------------------------------------------------------------
def prelim(src_file):
    global depth
    global nq
    global debug
    global nsamp

    depth = 0

    line = src_file.readline()
    if line[3:12] == 'max qubit':
        nq = int(line[12:])
    else:
        sys.stderr.write('Undefined max qubit\n')
        sys.exit(-1)

    line = src_file.readline()
    if line[3:12] ==  'ops count':
        len_in = int(line[12:])
    else:
        sys.stderr.write('Undefined ops count\n')
        sys.exit(-1)

    line = src_file.readline()
    if line[3:8] == 'shots':
        nsamp = int(line[8:])
        line = src_file.readline()

    if line[3:8] == 'debug':
        debug = 1
        line = src_file.readline()

    # The original Fortran code had some statements that appear to do
    # nothing and not contribute to the intent of the loop.
    if line[0:2] == 'op':
        depth += 1

    for line in src_file:
        if depth == len_in:
            sys.stderr.write('Runaway')
            sys.exit(-1)
        if line[0:2] == '//': continue
        if line[0:2] == 'op':
            depth = depth + 1

    if depth < len_in:
        sys.stderr.write('Warning: ops count too long\n')

#==========================================
# Extended parser for IonQ Quantum Cloud ::
# incompatiable with the optimizer yet,
# in particular due to swap, x, y, srn, not
# Also, the way that cnot's are handled
# has changed for the multi-controllability
#==========================================
#-------------------------
# Type of gates considered
#
# Hadamard, x, y, z, s, t, r2, r4, r8, rx, ry, rz, srn, not,
# swap, cswap, cnot, cx, cy, cz
#------------------------------
#-------------------------------------------------------
# See below for the interal representation of each gates
#-------------------------------------------------------
def read(src_file, igate_type, ang_rot, ioperand):
    index = -1
    src_file.seek(0)

    for line in src_file:
        if debug:
            print("reading line:" + line)
        if index == depth: break
        line = line.strip()
        if len(line) == 0: continue
        if line[0:2] != 'op': continue
        index = index + 1

        #-------------------------------------------
        # Extract control / target bracket locations
        #-------------------------------------------

        bracket_left = []
        bracket_right = []
        for pos in range(2, len(line)):
            c = line[pos]
            if (c == '['):
                bracket_left.append(pos)
     
            if (c == ']'):
                bracket_right.append(pos)
     
        if len(bracket_left) > 2 or len(bracket_right) > 2:
            sys.stderr.write('extra qubit type? :: control, target, ???\n')
            sys.exit(-1)

        if len(bracket_left) != len(bracket_right):
            sys.stderr.write('mismatched brackets')
            sys.exit(-1)
     
        ang = pi
        # If there are characters past the last right bracket on the line,
        # assume they are for the angle and try to read them.
        # TODO: what if there is a comment at the end of the line.
        if len(bracket_right) == 2 and bracket_right[1] < len(line)-1:
            ang = float(line[bracket_right[1] + 1 :])
        elif len(bracket_right) !=  2 and bracket_right[0] < len(line)-1:
            ang = float(line[bracket_right[0] + 1:])

        #==========
        # GATE TYPE
        #==========
        if (len(bracket_left) < 2):
            icont = 0 # no control
        else:
            icont = 1 # control

        if (line[3:4] == 'h'):
            igate_type[index] = 1
        elif (line[3:7] == 'swap'):
            igate_type[index] = 12
        elif (line[3:4] == 'x'):
            igate_type[index] = 2
            ang_rot[index] = ang
        elif (line[3:4] == 'y'):
            igate_type[index] = 13
            ang_rot[index] = ang
        elif (line[3:4] == 'z'):
            igate_type[index] = 5
            ang_rot[index] = ang
        elif (line[3:6] == 'not'):
            igate_type[index] = 2
            ang_rot[index] = pi
        elif (line[3:4] == 's' and line[3:7] !='swap'):
            if (line[4:5] == 'i'):
                igate_type[index] = 3
            else:
                igate_type[index] = 4
        elif (line[3:4] == 't'):
            if (line[4:5] == 'i'):
                igate_type[index] = 6
            else:
                igate_type[index] = 7
        elif (line[3:4] == 'v'):
            if (line[4:5] == 'i'):
                igate_type[index] = 14
            else:
                igate_type[index] = 15
        elif (line[3:5] == 'rx'):
            igate_type[index] = 16
            ang_rot[index] = ang
        elif (line[3:5] == 'ry'):
            igate_type[index] = 17
            ang_rot[index] = ang
        elif (line[3:5] == 'rz'):
            igate_type[index] = 18
            ang_rot[index] = ang
        else: # parser_break
            sys.stderr.write('unrecognizable gate by the parser\n')
            sys.stderr.write(line)
            sys.exit(-1)

        #=================
        # Operand QUBIT(s)
        #=================
        if (icont == 1): # Controlled
            #--------------------
            #     Read control qubits
            #--------------------
            ncont_left = bracket_left[1]
            for ncont_right in range(bracket_left[1]+1,bracket_right[1]):
                if (line[ncont_right] == ','):
                    ncont = int(line[ncont_left+1:ncont_right])
                    if (ncont !=0):
                        if (ncont > 0):
                            ioperand[index][abs(ncont)] = 2
                        else:
                            ioperand[index][abs(ncont)] = 3
                    else:
                        if (line[ncont_left+1:ncont_left+1] == '-'):
                            ioperand[index][abs(ncont)] = 3
                        else:
                            ioperand[index][abs(ncont)] = 2
                    ncont_left = ncont_right

                if (line[ncont_right+1] == ']'):
                    ncont = int(line[ncont_left + 1 : ncont_right + 1])
                    if (ncont != 0):
                        if (ncont > 0):
                            ioperand[index][abs(ncont)] = 2
                        else:
                            ioperand[index][abs(ncont)] = 3
                    else:
                        if (line[ncont_left+1] == '-'):
                            ioperand[index][abs(ncont)] = 3
                        else:
                            ioperand[index][abs(ncont)] = 2
                    break

        #-------------------
        #     Read target qubits
        #-------------------
        ntarg_left = bracket_left[0]
        for ntarg_right in range(bracket_left[0]+1, bracket_right[0]):
            if (line[ntarg_right] == ','):
                ntarg = int(line[ntarg_left+1:ntarg_right])
                ioperand[index][ntarg] = 1
                ntarg_left = ntarg_right

            if (line[ntarg_right+1] == ']'):
                ntarg = int(line[ntarg_left+1:ntarg_right+1])
                ioperand[index][ntarg] = 1
                break

def convert(igate_type, ang_rot, ioperand):
    ianc_avail = [1] * max_nq

    # SWAP

    nct_anc_avail = max_nq # number of clean ancilla available.

    for index in range(depth):
        # count the number of controls
        num_ccont = 0; num_ocont = 0
        for inq in range(nq):
            if (ioperand[index][inq] == 1): ntarg = inq
            if (ioperand[index][inq] == 2): num_ccont = num_ccont + 1
            if (ioperand[index][inq] == 3): num_ocont = num_ocont + 1
            if (ioperand[index][inq] !=0):
               if (ianc_avail[inq] == 1):
                  nct_anc_avail = nct_anc_avail-1
            if (ioperand[index][inq] !=0): ianc_avail[inq] = 0
        num_cont = num_ccont + num_ocont

        # check for the number of controls
        if (num_cont > num_cont_thres):
            sys.stderr.write("*** TOO MANY CONTROLS ***")
            sys.exit(-1)

         # check if a single not + basis transf. is sufficient
        if (num_cont != 0):
            not_single = 0
            if (igate_type[index] == 16 and
                abs(bmod(ang_rot[index]-pi,2*pi)) < diff_thres): not_single = 1 # RX
            if (igate_type[index] == 17  and
                abs(bmod(ang_rot[index]-pi,2*pi)) < diff_thres): not_single = 1 # RY
            if (igate_type[index] == 18  and
                abs(bmod(ang_rot[index]-pi,2*pi)) < diff_thres): not_single = 1 # RZ
            if (igate_type[index] == 2  and
                abs(bmod(ang_rot[index]-pi,2*pi)) < diff_thres): not_single = 1 # X
            if (igate_type[index] == 13  and
                abs(bmod(ang_rot[index]-pi,2*pi)) < diff_thres): not_single = 1 # Y
            if (igate_type[index] == 5  and
                abs(bmod(ang_rot[index]-pi,2*pi)) < diff_thres): not_single = 1 # Z
            if (igate_type[index] == 1): not_single = 1 # H
        else:
            idirect_impl = 0
            if (igate_type[index] == 1): idirect_impl = 1 # H
            if (igate_type[index] == 4): idirect_impl = 1 # S
            if (igate_type[index] == 3): idirect_impl = 1 # S*
            if (igate_type[index] == 7): idirect_impl = 1 # T
            if (igate_type[index] == 6): idirect_impl = 1 # T*
            if (igate_type[index] == 5): idirect_impl = 1 # Z
            if (igate_type[index] == 18): idirect_impl = 1 # RZ
            if (igate_type[index] == 2 and
                abs(bmod(ang_rot[index]-pi,2*pi)) < diff_thres): idirect_impl = 1 # X
            if (igate_type[index] == 16  and
                abs(bmod(ang_rot[index]-pi,2*pi)) < diff_thres): idirect_impl = 1 # RX

        ang = ang_rot[index]
        if (igate_type[index] == 4):
            ang = pi/2.0
        elif (igate_type[index] == 3):
            ang = -pi/2.0
        elif (igate_type[index] == 7):
            ang = pi/4.0
        elif (igate_type[index] == 6):
            ang = -pi/4.0
        elif (igate_type[index] == 15):
            ang = pi/2.0
        elif (igate_type[index] == 14):
            ang = -pi/2.0

         # top-level tree :: Number of controls
        if (num_cont == 0):
            if (igate_type[index] == 12):
                for inq in range(nq):
                    if (ioperand[index][inq] == 1):
                        itarg = inq
                        break
                inq_l = inq
                for inq in range(inq_l+1,nq):
                    if (ioperand[index][inq] == 1):
                        icont = inq
                        break
                cnot(icont,itarg)
                cnot(itarg,icont)
                cnot(icont,itarg)
                continue

            if (idirect_impl == 1):
                direct_single(igate_type[index],ntarg,ang)
            else:
                axis_transf_f(igate_type[index],ntarg) # To Z basis
                z_basis_gate(igate_type[index],ntarg,ang)
                axis_transf_b(igate_type[index],ntarg) # From Z basis

        else:
            # Preliminary swap support 
            # To be replaced with swap once relabeling is supported in the optimizer

            if (not_single == 0):
                axis_transf_f(igate_type[index],ntarg) # To Z basis
                if (igate_type[index] == 2 or igate_type[index] == 13
                    or igate_type[index] == 5 or igate_type[index] == 4
                    or igate_type[index] == 3 or igate_type[index] == 6
                    or igate_type[index] == 7 or igate_type[index] == 15
                    or igate_type[index] == 14):
                    multZ(ang,ioperand[index],num_cont,nct_anc_avail,ianc_avail)
                else:
                  multRZ(ang,ioperand[index],num_cont,nct_anc_avail,ianc_avail)

                axis_transf_b(igate_type[index],ntarg) # From Z basis
            else:
                axis_transf_f(igate_type[index],ntarg) # To Z basis
                hgate(ntarg)
                ntoff(ioperand[index],num_cont,nct_anc_avail,ianc_avail)
                hgate(ntarg)
                axis_transf_b(igate_type[index],ntarg) # From Z basis

def z_basis_gate(igate,ntarg,ang):
    if (abs(bmod(ang-pi,2*pi)) < diff_thres):
        zgate(ntarg)
    elif (abs(bmod(ang-pi/2.0,2*pi)) < diff_thres):
        sgate(ntarg)
    elif (abs(bmod(ang+pi/2.0,2*pi)) < diff_thres):
        sdagger(ntarg)
    elif (abs(bmod(ang-pi/4.0,2*pi)) < diff_thres):
        tgate(ntarg)
    elif (abs(bmod(ang+pi/4.0,2*pi)) < diff_thres):
        tdagger(ntarg)
    else:
        z(ntarg,ang)

# Returns a balanced (a mod b), within the range [-b/2, b/2)
# Unlike MOD, this is NOT necessarily the same sign as the input
def bmod(a: float, b: float):
    c = a % b
    d = abs(b * 0.5)
    if (c >=d):
        return (c- b)
    elif (c < (-d)):
        return (c + b)
    else:
        return (c)

#------------------------------------------
# Directly implementable single-qubit gates
#------------------------------------------
def direct_single(igate, ntarg, ang):
    if (igate == 1): # H
        hgate(ntarg)
    elif (igate == 4): # S
        sgate(ntarg)
    elif (igate == 3): # S*
        sdagger(ntarg)
    elif (igate == 7): # T
        tgate(ntarg)
    elif (igate == 6): # T*
        tdagger(ntarg)
    elif (igate == 5): # Z
        if (abs(bmod(ang-4.0 * math.atan(1.0),8.0*math.atan(1.0))) < diff_thres):
            zgate(ntarg)
        else:
            z(ntarg,ang)
    elif (igate == 18): # RZ (GPHASE)
        if (abs(bmod(ang-4.0 * math.atan(1.0),8.0*math.atan(1.0))) < diff_thres):
            zgate(ntarg)
        else:
            z(ntarg,ang)
    elif (igate == 2): # X(pi)
        xgate(ntarg)
    elif (igate == 16): # RX(pi) (GPHASE)
        xgate(ntarg)

def axis_transf_f(igate,ntarg):
# To Z-basis
    if (igate == 1): # H
        sdagger(ntarg)
        hgate(ntarg)
        tdagger(ntarg)
        hgate(ntarg)
    elif (igate == 2): # X
        hgate(ntarg)
    elif (igate == 13): # Y
        sdagger(ntarg)
        hgate(ntarg)
    elif (igate == 15): # V
        hgate(ntarg)
    elif (igate == 14): # V*
        hgate(ntarg)
    elif (igate == 16): # RX
        hgate(ntarg)
    elif (igate == 17): # RY
        sdagger(ntarg)
        hgate(ntarg)

def axis_transf_b(igate,ntarg):
    # From Z-basis
    #-------------
    if (igate == 1): # H
        hgate(ntarg)
        tgate(ntarg)
        hgate(ntarg)
        sgate(ntarg)
    elif (igate == 2): # X
        hgate(ntarg)
    elif (igate == 13): # Y
        hgate(ntarg)
        sgate(ntarg)
    elif (igate == 15): # V
        hgate(ntarg)
    elif (igate == 14): # V*
        hgate(ntarg)
    elif (igate == 16): # RX
        hgate(ntarg)
    elif (igate == 17): # RY
        hgate(ntarg)
        sgate(ntarg)

def phase_boolsum(ang,ntarg,ioperand,num_cont,nanc_avail,ianc_avail):
    ntoff(ioperand,num_cont,nanc_avail,ianc_avail) # to target
    z(ntarg,ang)
    ntoff(ioperand,num_cont,nanc_avail,ianc_avail) # to target

def multRZ(ang,ioperand,num_cont,nanc_avail,ianc_avail):
    for inq in range(nq):
        if (ioperand[inq] == 1): ntarg = inq
        if (ioperand[inq] == 3): xgate(inq)

    ang = ang/2.0
    phase_boolsum(-ang,ntarg,ioperand,num_cont,nanc_avail,ianc_avail)
    z(ntarg,ang)

    for inq in range(nq):
        if (ioperand[inq] == 3): xgate(inq)

def multZ(ang,ioperand,num_cont,nanc_avail,ianc_avail):
    assert(len(ioperand) == max_nq and len(ianc_avail) == max_nq)

    for inq in range(nq):
        if (ioperand[inq] == 1): ntarg = inq
        if (ioperand[inq] == 3): xgate(inq)

    if (nanc_avail == 0):
        num_cont_tr = num_cont
        while (1):  # until 1 control
            ang = ang/2.0
            phase_boolsum(-ang,ntarg,ioperand,num_cont_tr,nanc_avail,ianc_avail)
            z(ntarg,ang) # on the current target

            # Update ioperand and ntarg
            iqb = 0
            for inq in range(nq):
                if (ioperand[inq] == 2 or ioperand[inq] == 3):
                    if (iqb == 0):
                        ntarg = inq
                        ioperand[inq] = 1
                    iqb = iqb + 1
            num_cont_tr = iqb - 1

            # no more phase_boolsum
            if (num_cont_tr == 0): break
        z(ntarg,ang)
    else:
        if (num_cont > 1):
            ioperand_str = copy.deepcopy(ioperand)
            ntarg_str = ntarg
            num_cont_str = num_cont

            # First available Ancilla
            for inq in range(max_nq):
                if (ianc_avail[inq] == 1): break
            nanc = inq

            ## CHANGE THE TARGET TO ANCILLA ##
            ntarg = nanc
            nanc_avail = nanc_avail-1
            ianc_avail[nanc] = 0

            num_cont = num_cont_str
            ioperand = [0] * len(ioperand)
            for inq in range(max_nq):
                if (inq == ntarg): ioperand[inq] = 1
                if (ioperand_str[inq] == 2): ioperand[inq] = 2
                if (ioperand_str[inq] == 3): ioperand[inq] = 3

            ntoff(ioperand,num_cont,nanc_avail,ianc_avail) # to ancilla

            ncont = ntarg
            ntarg = ntarg_str

            ioperand = [0] * len(ioperand)
            ioperand[ntarg] = 1
            ioperand[ncont] = 2
            num_cont = 1

            ang = ang/2.0
            phase_boolsum(-ang,ntarg,ioperand,num_cont,nanc_avail,ianc_avail)
            z(ntarg,ang) # on the current target
            z(ncont,ang) # on the current control

            ## CHANGE THE TARGET TO ANCILLA ##
            ntarg = nanc
            num_cont = num_cont_str
            ioperand = [0] * len(ioperand)
            for inq in range(max_nq):
                if (inq == ntarg): ioperand[inq] = 1
                if (ioperand_str[inq] == 2): ioperand[inq] = 2
                if (ioperand_str[inq] == 3): ioperand[inq] = 3

            ntoff(ioperand,num_cont,nanc_avail,ianc_avail) # to ancilla

            nanc_avail = nanc_avail+1
            ianc_avail[nanc] = 1
            
            ioperand = ioperand_str
        else: # 1 control
            for inq in range(nq):
                if (ioperand[inq] == 2): ncont = inq
                if (ioperand[inq] == 3): ncont = inq

            ang = ang/2.0
            phase_boolsum(-ang,ntarg,ioperand,num_cont,nanc_avail,ianc_avail)
            z(ntarg,ang) # on the current target
            z(ncont,ang) # on the current control

    for inq in range(nq):
        if (ioperand[inq] == 3): xgate(inq)

def ntoff(ioperand,num_cont,nanc_avail,ianc_avail):
    assert(len(ioperand) == max_nq)
    assert(len(ianc_avail) == max_nq)

    nq_reg = [0] * (num_cont + 1)
    icont = 0
    for inq in range(max_nq):
        if (ioperand[inq] == 1): nq_reg[num_cont] = inq
        if (ioperand[inq] == 2): nq_reg[icont] = inq
        if (ioperand[inq] == 3): nq_reg[icont] = inq
        if (ioperand[inq] == 2): icont = icont + 1
        if (ioperand[inq] == 3): icont = icont + 1
        if (ioperand[inq] == 3): xgate(inq)

    if (num_cont == 7):
        if (nanc_avail >=3):
            # 3 Clean ancillas :: cost = 30 CNOTs
            nanc_c_reg = [0] * 3
            c_ancilla_choose(3,nanc_c_reg,ianc_avail)
            toff8c3d0(nq_reg,nanc_c_reg)
        elif (nanc_avail == 2):
            # 2 Clean ancillas :: cost = 32 CNOTs
            nanc_c_reg = [0] * 2
            c_ancilla_choose(2,nanc_c_reg,ianc_avail)
            toff8c2d0(nq_reg,nanc_c_reg)
        elif (nanc_avail == 1):
            # 1 Clean ancilla :: cost = 40 CNOTs
            nanc_c_reg = [0]
            c_ancilla_choose(1,nanc_c_reg,ianc_avail)
            toff8c1d0(nq_reg,nanc_c_reg)
        else:
            # 3 Dirty ancillas :: cost 44 CNOTs
            nanc_d_reg = [0] * 3
            d_ancilla_choose(3,nanc_d_reg,ioperand)
            toff8c0d3(nq_reg,nanc_d_reg)
    elif (num_cont == 6):
        if (nanc_avail >=2):
            # 2 Clean ancillas :: cost = 30 CNOTs
            nanc_c_reg = [0] * 2
            c_ancilla_choose(2,nanc_c_reg,ianc_avail)
            toff7c2d0(nq_reg,nanc_c_reg)
        elif (nanc_avail == 1):
            # 1 Clean ancilla :: cost = 32 CNOTs
            nanc_c_reg = [0]
            c_ancilla_choose(1,nanc_c_reg,ianc_avail)
            toff7c1d0(nq_reg,nanc_c_reg)
        else:
            # 2 Dirty ancillas :: cost = 36 CNOTs
            nanc_c_reg = [0] * 2
            d_ancilla_choose(2,nanc_d_reg,ioperand)
            toff7c0d2(nq_reg,nanc_d_reg)
    elif (num_cont == 5):
        if (nanc_avail >=2):
            # 2 Clean ancillas :: cost = 24 CNOTs
            nanc_c_reg = [0] * 2
            c_ancilla_choose(2,nanc_c_reg,ianc_avail)
            toff6c2d0(nq_reg,nanc_c_reg)
        elif (nanc_avail == 1):
        # 1 Clean ancilla :: cost = 26 CNOTs
            nanc_c_reg = [0]
            c_ancilla_choose(1,nanc_c_reg,ianc_avail)
            toff6c1d0(nq_reg,nanc_c_reg)
        else:
        # 2 Dirty ancillas :: cost = 28 CNOTs
            nanc_d_reg = [0] * 2
            d_ancilla_choose(2,nanc_d_reg,ioperand)
            toff6c0d2(nq_reg,nanc_d_reg)
    elif (num_cont == 4):
        if (nanc_avail >= 1):
            # 1 Clean ancilla :: cost = 18 CNOTs
            nanc_c_reg = [0]
            c_ancilla_choose(1,nanc_c_reg,ianc_avail)
            toff5c1d0(nq_reg,nanc_c_reg)
        else:
            # 1 Dirty ancilla :: cost = 20 CNOTs
            nanc_d_reg = [0]
            d_ancilla_choose(1,nanc_d_reg,ioperand)
            toff5c0d1(nq_reg,nanc_d_reg)
    elif (num_cont == 3):
        if (nanc_avail >= 1):
            # 1 Clean ancilla :: cost = 12 CNOTs
            nanc_c_reg = [0]
            c_ancilla_choose(1,nanc_c_reg,ianc_avail)
            toff4c1d0(nq_reg,nanc_c_reg)
        else:
            # 1 Dirty ancilla :: cost = 14 CNOTs
            nanc_d_reg = [0]
            d_ancilla_choose(1,nanc_d_reg,ioperand)
            toff4c0d1(nq_reg,nanc_d_reg)
    elif (num_cont == 2):
        # No ancilla :: cost = 6 CNOTs
        tof(nq_reg[0],nq_reg[1],nq_reg[2])
    elif (num_cont == 1):
        cnot(nq_reg[0],nq_reg[1])

    for inq in range(nq):
        if (ioperand[inq] == 3): xgate(inq)

def c_ancilla_choose(nanc,nanc_c_reg,ianc_avail):
    assert len(nanc_c_reg) == nanc and len(ianc_avail) == max_nq

    ianc_ct = 0
    for inq in range(max_nq):
        if (ianc_avail[inq] == 1):
            nanc_c_reg[ianc_ct] = inq
            ianc_ct = ianc_ct + 1
        if (ianc_ct == nanc): break
    assert ianc_ct == nanc, "Unable to choose ancilla"

def d_ancilla_choose(nanc,nanc_d_reg,ioperand):
    assert(len(nanc_d_reg) == nanc and len(ioperand) == max_nq)

    ianc_ct = 0
    for inq in range(max_nq):
        if (ioperand[inq] == 0):
            nanc_d_reg[ianc_ct] = inq
            ianc_ct = ianc_ct + 1
        if (ianc_ct == nanc): break
    assert ianc_ct == nanc, "Unable to choose ancilla"

#============================
# Multi-control Toffoli gates
#============================
def toff3c0d0(nq1,nq2,nq3):
    hgate(nq3)
    cnot(nq2,nq3)
    tdagger(nq3)
    cnot(nq1,nq3)
    tgate(nq3)
    cnot(nq2,nq3)
    tdagger(nq3)
    cnot(nq1,nq3)
    tgate(nq3)
    hgate(nq3)
    tgate(nq1)
    tgate(nq2)
    cnot(nq1,nq2)
    tdagger(nq2)
    cnot(nq1,nq2)

def toff4c0d1(nq_reg,na_d_reg):
    assert(len(nq_reg) == 4 and len(na_d_reg) == 1)

    rtl(nq_reg[0],nq_reg[1],na_d_reg[0])
    srts(nq_reg[2],na_d_reg[0],nq_reg[3])
    rtl_inv(nq_reg[0],nq_reg[1],na_d_reg[0])
    srts_inv(nq_reg[2],na_d_reg[0],nq_reg[3])

def toff4c1d0(nq_reg,na_c_reg):
    assert(len(nq_reg) == 4 and len(na_c_reg) == 1)

    rtl(nq_reg[0],nq_reg[1],na_c_reg[0])
    tof(na_c_reg[0],nq_reg[2],nq_reg[3])
    rtl_inv(nq_reg[0],nq_reg[1],na_c_reg[0])

def toff5c0d1(nq_reg,na_d_reg):
    assert(len(nq_reg) == 5 and len(na_d_reg) == 1)

    rt4l(nq_reg[0],nq_reg[1],nq_reg[2],na_d_reg[0])
    srts(nq_reg[3],na_d_reg[0],nq_reg[4])
    rt4l_inv(nq_reg[0],nq_reg[1],nq_reg[2],na_d_reg[0])
    srts_inv(nq_reg[3],na_d_reg[0],nq_reg[4])

def toff5c1d0(nq_reg,na_c_reg):
    assert(len(nq_reg) == 5 and len(na_c_reg) == 1)

    rt4l(nq_reg[0],nq_reg[1],nq_reg[2],na_c_reg[0])
    tof(na_c_reg[0],nq_reg[3],nq_reg[4])
    rt4l_inv(nq_reg[0],nq_reg[1],nq_reg[2],na_c_reg[0])

def toff6c0d2(nq_reg,na_d_reg):
    assert(len(nq_reg) == 5 and len(na_d_reg) == 2)

    srts(nq_reg[4],na_d_reg[1],nq_reg[5])
    rts(na_d_reg[0],nq_reg[3],na_d_reg[1])
    rt4l(nq_reg[0],nq_reg[1],nq_reg[2],na_d_reg[0])
    rts_inv(na_d_reg[0],nq_reg[3],na_d_reg[1])
    srts_inv(nq_reg[4],na_d_reg[1],nq_reg[5])
    rts(na_d_reg[0],nq_reg[3],na_d_reg[1])
    rt4l_inv(nq_reg[0],nq_reg[1],nq_reg[2],na_d_reg[0])
    rts_inv(na_d_reg[0],nq_reg[3],na_d_reg[1])

def toff6c1d0(nq_reg,na_c_reg):
    assert(len(nq_reg) == 6 and len(na_c_reg) == 1)

    rt4l(nq_reg[0],nq_reg[1],nq_reg[2],na_c_reg[0])
    ntof_reg = [nq_reg[3], nq_reg[4], na_c_reg[0], nq_reg[5]]
    nanc_d_reg = [nq_reg[2]]
    toff4c0d1(ntof_reg,nanc_d_reg)
    rt4l_inv(nq_reg[0],nq_reg[1],nq_reg[2],na_c_reg[0])

def toff6c2d0(nq_reg,na_c_reg):
    assert(len(nq_reg) == 6 and len(na_c_reg) == 2)

    rt4l(nq_reg[0],nq_reg[1],nq_reg[2],na_c_reg[0])
    ntof_reg = [nq_reg[3], nq_reg[4], na_c_reg[0], nq_reg[5]]
    nanc_c_reg = [na_c_reg[1]]
    toff4c1d0(ntof_reg,nanc_c_reg)
    rt4l_inv(nq_reg[0],nq_reg[1],nq_reg[2],na_c_reg[0])

def toff7c0d2(nq_reg,na_d_reg):
    assert(len(nq_reg) == 7 and len(na_d_reg) == 2)

    srts(nq_reg[5],na_d_reg[1],nq_reg[6])
    rt4s(na_d_reg[0],nq_reg[3],nq_reg[4],na_d_reg[1])
    rt4l(nq_reg[0],nq_reg[1],nq_reg[2],na_d_reg[0])
    rt4s_inv(na_d_reg[0],nq_reg[3],nq_reg[4],na_d_reg[1])
    srts_inv(nq_reg[5],na_d_reg[1],nq_reg[6])
    rt4s(na_d_reg[0],nq_reg[3],nq_reg[4],na_d_reg[1])
    rt4l_inv(nq_reg[0],nq_reg[1],nq_reg[2],na_d_reg[0])
    rt4s_inv(na_d_reg[0],nq_reg[3],nq_reg[4],na_d_reg[1])

def toff7c1d0(nq_reg,na_c_reg):
    assert(len(nq_reg) == 7 and len(na_c_reg) == 1)

    rt4l(nq_reg[0],nq_reg[1],nq_reg[2],na_c_reg[0])
    ntof_reg = [nq_reg[3], nq_reg[4], nq_reg[5], na_c_reg[0], nq_reg[6]]
    nanc_d_reg = [nq_reg[2]]
    toff5c0d1(ntof_reg,nanc_d_reg)
    rt4l_inv(nq_reg[0],nq_reg[1],nq_reg[2],na_c_reg[0])

def toff7c2d0(nq_reg,na_c_reg):
    assert(len(nq_reg) == 7 and len(na_c_reg) == 2)

    rt4l(nq_reg[0],nq_reg[1],nq_reg[2],na_c_reg[0])
    rt4l(nq_reg[3],nq_reg[4],na_c_reg[0],na_c_reg[1])
    tof(nq_reg[5],na_c_reg[1],nq_reg[6])
    rt4l_inv(nq_reg[3],nq_reg[4],na_c_reg[0],na_c_reg[1])
    rt4l_inv(nq_reg[0],nq_reg[1],nq_reg[2],na_c_reg[0])

def toff8c0d3(nq_reg,na_d_reg):
    assert(len(nq_reg) == 8 and len(na_d_reg) == 3)

    srts(nq_reg[6],na_d_reg[2],nq_reg[7])
    rts(na_d_reg[1],nq_reg[5],na_d_reg[2])
    rt4s(na_d_reg[0],nq_reg[3],nq_reg[4],na_d_reg[1])
    rt4l(nq_reg[0],nq_reg[1],nq_reg[2],na_d_reg[0])
    rt4s_inv(na_d_reg[0],nq_reg[3],nq_reg[4],na_d_reg[1])
    rts_inv(na_d_reg[1],nq_reg[5],na_d_reg[2])
    srts_inv(nq_reg[6],na_d_reg[2],nq_reg[7])
    rts(na_d_reg[1],nq_reg[5],na_d_reg[2])
    rt4s(na_d_reg[0],nq_reg[3],nq_reg[4],na_d_reg[1])
    rt4l_inv(nq_reg[0],nq_reg[1],nq_reg[2],na_d_reg[0])
    rt4s_inv(na_d_reg[0],nq_reg[3],nq_reg[4],na_d_reg[1])
    rts_inv(na_d_reg[1],nq_reg[5],na_d_reg[2])

def toff8c1d0(nq_reg,na_c_reg):
    assert(len(nq_reg) == 8 and len(na_c_reg) == 1)

    rt4l(nq_reg[0],nq_reg[1],nq_reg[2],na_c_reg[0])
    ntof_reg = [nq_reg[3], nq_reg[4], nq_reg[5], nq_reg[6], na_c_reg[0], nq_reg[7]]
    nanc_d_reg = [nq_reg[2], nq_reg[1]]
    toff6c0d2(ntof_reg,nanc_d_reg)
    rt4l_inv(nq_reg[0],nq_reg[1],nq_reg[2],na_c_reg[0])

def toff8c2d0(nq_reg,na_c_reg):
    assert(len(nq_reg) == 8 and len(na_c_reg) == 2)

    rt4l(nq_reg[0],nq_reg[1],nq_reg[2],na_c_reg[0])
    rt4l(nq_reg[3],nq_reg[4],nq_reg[5],na_c_reg[1])
    ntof_reg = [nq_reg[6], na_c_reg[0], na_c_reg[1], nq_reg[7]]
    nanc_d_reg = [nq_reg[5]]
    toff4c0d1(ntof_reg,nanc_d_reg)
    rt4l_inv(nq_reg[3],nq_reg[4],nq_reg[5],na_c_reg[1])
    rt4l_inv(nq_reg[0],nq_reg[1],nq_reg[2],na_c_reg[0])

def toff8c3d0(nq_reg,na_c_reg):
    assert(len(nq_reg) == 8 and len(na_c_reg) == 3)

    rt4l(nq_reg[0],nq_reg[1],nq_reg[2],na_c_reg[0])
    rt4l(nq_reg[3],nq_reg[4],nq_reg[5],na_c_reg[1])
    ntof_reg = [nq_reg[6], na_c_reg[0], na_c_reg[1], nq_reg[7]]
    nanc_c_reg = [na_c_reg[2]]
    toff4c1d0(ntof_reg,nanc_c_reg)

    rt4l_inv(nq_reg[3],nq_reg[4],nq_reg[5],na_c_reg[1])
    rt4l_inv(nq_reg[0],nq_reg[1],nq_reg[2],na_c_reg[0])

#============================
# Some supplementary gates ..
#============================
def rtl(nq1,nq2,nq3):
    hgate(nq3)
    tgate(nq3)
    cnot(nq2,nq3)
    tdagger(nq3)
    cnot(nq1,nq3)
    tgate(nq3)
    cnot(nq2,nq3)
    tdagger(nq3)
    hgate(nq3)

def rtl_inv(nq1,nq2,nq3):
    hgate(nq3)
    tgate(nq3)
    cnot(nq2,nq3)
    tdagger(nq3)
    cnot(nq1,nq3)
    tgate(nq3)
    cnot(nq2,nq3)
    tdagger(nq3)
    hgate(nq3)

def rts(nq1,nq2,nq3):
    hgate(nq3)
    tgate(nq3)
    cnot(nq2,nq3)
    tdagger(nq3)
    cnot(nq1,nq3)

def rts_inv(nq1,nq2,nq3):
    cnot(nq1,nq3)
    tgate(nq3)
    cnot(nq2,nq3)
    tdagger(nq3)
    hgate(nq3)

def srts(nq1,nq2,nq3):
    hgate(nq3)
    cnot(nq3,nq2)
    tdagger(nq2)
    cnot(nq1,nq2)
    tgate(nq2)
    cnot(nq3,nq2)
    tdagger(nq2)
    cnot(nq1,nq2)
    tgate(nq2)

def srts_inv(nq1,nq2,nq3):
    tdagger(nq2)
    cnot(nq1,nq2)
    tgate(nq2)
    cnot(nq3,nq2)
    tdagger(nq2)
    cnot(nq1,nq2)
    tgate(nq2)
    cnot(nq3,nq2)
    hgate(nq3)

def rt4l(nq1,nq2,nq3,nq4):
    hgate(nq4)
    tgate(nq4)
    cnot(nq3,nq4)
    tdagger(nq4)
    hgate(nq4)
    cnot(nq1,nq4)
    tgate(nq4)
    cnot(nq2,nq4)
    tdagger(nq4)
    cnot(nq1,nq4)
    tgate(nq4)
    cnot(nq2,nq4)
    tdagger(nq4)
    hgate(nq4)
    tgate(nq4)
    cnot(nq3,nq4)
    tdagger(nq4)
    hgate(nq4)

def rt4l_inv(nq1,nq2,nq3,nq4):
    hgate(nq4)
    tgate(nq4)
    cnot(nq3,nq4)
    tdagger(nq4)
    hgate(nq4)
    tgate(nq4)
    cnot(nq2,nq4)
    tdagger(nq4)
    cnot(nq1,nq4)
    tgate(nq4)
    cnot(nq2,nq4)
    tdagger(nq4)
    cnot(nq1,nq4)
    hgate(nq4)
    tgate(nq4)
    cnot(nq3,nq4)
    tdagger(nq4)
    hgate(nq4)

def rt4s(nq1,nq2,nq3,nq4):
    hgate(nq4)
    tgate(nq4)
    cnot(nq3,nq4)
    tdagger(nq4)
    hgate(nq4)
    cnot(nq1,nq4)
    tgate(nq4)
    cnot(nq2,nq4)
    tdagger(nq4)
    cnot(nq1,nq4)

def rt4s_inv(nq1,nq2,nq3,nq4):
    cnot(nq1,nq4)
    tgate(nq4)
    cnot(nq2,nq4)
    tdagger(nq4)
    cnot(nq1,nq4)
    hgate(nq4)
    tgate(nq4)
    cnot(nq3,nq4)
    tdagger(nq4)
    hgate(nq4)

#===============
# Basis gates ..
#===============
def hgate(itarg):
    current_output.write('op h [{}]\n'.format(itarg))

def xgate(itarg):
    current_output.write('op x [{}]\n'.format(itarg))

def zgate(itarg):
    current_output.write('op z [{}]\n'.format(itarg))

def sgate(itarg):
    current_output.write('op s [{}]\n'.format(itarg))

def tgate(itarg):
    current_output.write('op t [{}]\n'.format(itarg))

def sdagger(itarg):
    current_output.write('op si [{}]\n'.format(itarg))

def tdagger(itarg):
    current_output.write('op ti [{}]\n'.format(itarg))

def z(itarg, ang: float):
    current_output.write('op z [{}] {}\n'.format(itarg, ang))

def cnot(icont,itarg):
    current_output.write('op not [{}] [{}]\n'.format(itarg, icont))

def tof(icont1,icont2,itarg):
#      itof_count  = itof_count +
#  1   current_output.write('op not [{}] [{}, {}] \n'.format(itarg, icont1, icont2))
#
    toff3c0d0(icont1,icont2,itarg)

if __name__ == '__main__':
    sys.exit(main(sys.argv))