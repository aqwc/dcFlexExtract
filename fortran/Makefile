# Makefile for calc_etadot in dcFlexExtract.
# Adapted from flex_extract's Source/Fortran/makefile_local_gfortran_new
# (Copyright: Leopold Haimberger, Petra Seibert; SPDX-License-Identifier: GPL-2.0).
# Changes: ecCodes found via pkg-config / ECCODES_DIR, EMOS replaced by fft99_lite.f90 (optional USE_EMOS=1).
# SPDX-License-Identifier: GPL-2.0-only
# See NOTICE.md.

# calc_etadot for dcFlexExtract. Needs gfortran and ecCodes with its Fortran interface.
# ecCodes is found via pkg-config (eccodes_f90), or set ECCODES_DIR=/path/to/eccodes (its include/ and lib/).
FC      = gfortran
OPT     ?= -O3
ifdef ECCODES_DIR
  ECINC := -I$(ECCODES_DIR)/include
  ECLIB := -L$(ECCODES_DIR)/lib -L$(ECCODES_DIR)/lib64 -leccodes_f90 -leccodes
else
  ECINC := $(shell pkg-config --cflags eccodes_f90) $(addprefix -I,$(wildcard /usr/lib/$(shell gfortran -dumpmachine)/fortran/gfortran-mod-*))
  ECLIB := $(shell pkg-config --libs eccodes_f90)
endif
# FFT99/SET99 come from fft99_lite.f90 (no EMOS needed). `make USE_EMOS=1` links libemosR64 instead
# (EMOS_DIR=/path/with/lib if not on standard paths), e.g. for comparisons.
ifdef USE_EMOS
  EMOSLIB = $(if $(EMOS_DIR),-L$(EMOS_DIR)/lib -L$(EMOS_DIR),) -lemosR64
else
  EMOSLIB =
  FFTOBJ  = fft99_lite.o
endif
FFLAGS  = $(OPT) $(ECINC) -I. -fdefault-real-8 -fopenmp -fconvert=big-endian
LDFLAGS = $(OPT) -fopenmp
OBJ     = rwgrib2.o calc_etadot.o ftrafo.o grphreal.o phgrreal.o $(FFTOBJ)

all: calc_etadot

calc_etadot: $(OBJ)
	$(FC) $(OBJ) -o $@ $(LDFLAGS) $(ECLIB) $(EMOSLIB) -lm

ftrafo.o grphreal.o: phgrreal.o
calc_etadot.o: phgrreal.o grphreal.o ftrafo.o rwgrib2.o
%.o: %.f90
	$(FC) $(FFLAGS) -c $<

clean:
	rm -f *.o *.mod calc_etadot
