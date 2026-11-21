! dcFlexExtract - Copyright (C) 2026 the dcFlexExtract contributors
! SPDX-License-Identifier: CC-BY-4.0

! Prints SET99/FFT99 results for fixed pseudo-random input; linked once with EMOS and once with
! fft99_lite.f90 to compare them.
program drv
  implicit none
  integer, parameter :: ns(8) = (/ 6, 8, 10, 16, 36, 90, 720, 1440 /)
  integer :: ii, n, i, ifax(10), isign
  real, allocatable :: a(:), w(:), trigs(:)
  do ii = 1, size(ns)
    n = ns(ii)
    allocate(a(0:n+1), w(2*n+15), trigs(4*n+15))
    call set99(trigs, ifax, n)
    do isign = 1, -1, -2
      do i = 0, n + 1
        a(i) = sin(1.37d0 * i) + 0.3d0 * cos(0.11d0 * i * i)
      end do
      if (isign > 0) then
        a(1) = 0.0d0; a(n+1) = 0.0d0
      end if
      call fft99(a, w, trigs, ifax, 1, 1, n, 1, isign)
      write(*,'(A,I5,A,I3)') 'n=', n, ' isign=', isign
      do i = 1, n
        write(*,'(ES24.15)') a(i)
      end do
      if (isign > 0) then
        write(*,'(ES24.15)') a(0)
      end if
    end do
    deallocate(a, w, trigs)
  end do
end program
