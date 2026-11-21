! dcFlexExtract - Copyright (C) 2026 the dcFlexExtract contributors
! SPDX-License-Identifier: CC-BY-4.0
! Written for dcFlexExtract as an independent replacement for the two ECMWF EMOS routines used by
! calc_etadot (SET99, FFT99); it contains no EMOS code (behaviour was determined by comparing results
! with EMOS, see tests/test_fft99_lite.sh). See NOTICE.md.

! Minimal replacement for the two EMOS routines used by calc_etadot: SET99 and FFT99, restricted to
! the way calc_etadot calls them (one row at a time: inc = 1, jump = 1, lot = 1, even n).
! Verified against libemos for several n (see tests/test_fft99_lite.sh).
!
! Layout (as in EMOS): coefficients a(0:n+1) = [a0, b0, a1, b1, ..., a(n/2), b(n/2)], grid values
! x(0:n-1) are held in a(1:n); a(0) and a(n+1) receive the periodic extension.
!   isign = +1 (coefficients -> grid):
!     x(j) = a0 + sum_{k=1}^{n/2-1} 2 (a_k cos(2 pi k j/n) - b_k sin(2 pi k j/n)) + a_{n/2} (-1)^j
!   isign = -1 (grid -> coefficients):
!     a_k = (1/n) sum_j x(j) cos(2 pi k j/n),  b_k = -(1/n) sum_j x(j) sin(2 pi k j/n)
! TRIGS and IFAX are NOT used: calc_etadot calls FFT99 in some code paths without ever calling SET99
! (EMOS tolerates that), so the cos/sin table is rebuilt inside every call (n evaluations, negligible
! next to the O(n^2) sums).

SUBROUTINE SET99(TRIGS, IFAX, N)
  ! kept for the call sites; nothing to precompute (see above)
  IMPLICIT NONE
  INTEGER :: N, IFAX(10)
  REAL :: TRIGS(*)
  IF (MOD(N, 2) /= 0) THEN
    WRITE(*,*) 'SET99 (fft99_lite): n must be even, got', N
    STOP 1
  END IF
  IFAX = 0
  TRIGS(1) = 0.0
END SUBROUTINE SET99

SUBROUTINE FFT99(A, WORK, TRIGS, IFAX, INC, JUMP, N, LOT, ISIGN)
  IMPLICIT NONE
  INTEGER :: INC, JUMP, N, LOT, ISIGN, IFAX(10), J, K, IDX, H
  REAL :: A(0:*), WORK(*), TRIGS(*)
  REAL :: ACOEF(0:N/2), BCOEF(0:N/2), X(0:N-1), S, TWOPI
  REAL :: CS(0:N-1), SN(0:N-1)
  IF (INC /= 1 .OR. LOT /= 1 .OR. MOD(N, 2) /= 0) THEN
    WRITE(*,*) 'FFT99 (fft99_lite): only inc=1, lot=1 and even n are supported'
    STOP 1
  END IF
  TWOPI = 8.0 * ATAN(1.0)
  DO J = 0, N - 1
    CS(J) = COS(TWOPI * J / N)
    SN(J) = SIN(TWOPI * J / N)
  END DO
  H = N / 2
  IF (ISIGN > 0) THEN
    DO K = 0, H
      ACOEF(K) = A(2 * K)
      BCOEF(K) = A(2 * K + 1)
    END DO
    DO J = 0, N - 1
      S = ACOEF(0)
      DO K = 1, H - 1
        IF (ACOEF(K) == 0.0 .AND. BCOEF(K) == 0.0) CYCLE
        IDX = MOD(K * J, N)
        S = S + 2.0 * (ACOEF(K) * CS(IDX) - BCOEF(K) * SN(IDX))
      END DO
      IF (MOD(J, 2) == 0) THEN
        S = S + ACOEF(H)
      ELSE
        S = S - ACOEF(H)
      END IF
      X(J) = S
    END DO
    DO J = 0, N - 1
      A(J + 1) = X(J)
    END DO
    A(0) = X(N - 1)
    A(N + 1) = X(0)
  ELSE
    DO J = 0, N - 1
      X(J) = A(J + 1)
    END DO
    DO K = 0, H
      ACOEF(K) = 0.0
      BCOEF(K) = 0.0
      DO J = 0, N - 1
        IDX = MOD(K * J, N)
        ACOEF(K) = ACOEF(K) + X(J) * CS(IDX)
        BCOEF(K) = BCOEF(K) - X(J) * SN(IDX)
      END DO
      ACOEF(K) = ACOEF(K) / N
      BCOEF(K) = BCOEF(K) / N
    END DO
    BCOEF(0) = 0.0
    BCOEF(H) = 0.0
    DO K = 0, H
      A(2 * K) = ACOEF(K)
      A(2 * K + 1) = BCOEF(K)
    END DO
  END IF
END SUBROUTINE FFT99

SUBROUTINE JSPPOLE(XMN, ISIGN, MNAUF, LOGI, CPOLE)
  ! EMOS routine used only in the gaussian-grid branch (MGAUSS=1), which dcFlexExtract never uses.
  IMPLICIT NONE
  INTEGER :: ISIGN, MNAUF
  LOGICAL :: LOGI
  REAL :: XMN(*), CPOLE(*)
  WRITE(*,*) 'ERROR: gaussian-grid mode (mgauss=1) is not supported without EMOS (JSPPOLE)'
  STOP 1
END SUBROUTINE JSPPOLE
