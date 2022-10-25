%global package_speccommit c435d9d005a53a9e0cca15ba7018581168166d47
%global package_srccommit v1.0.0
Name: varstored
Summary: EFI Variable Storage Daemon
Version: 1.0.0
Release: 2%{?xsrel}%{?dist}

License: BSD
Source0: varstored-1.0.0.tar.gz

BuildRequires: xen-libs-devel xen-dom0-libs-devel openssl openssl-devel libxml2-devel
BuildRequires: glib2-devel
BuildRequires: libseccomp-devel
BuildRequires: gcc
%{?_cov_buildrequires}


Requires: varstored-guard secureboot-certificates

%description
A daemon for implementing variable services for UEFI guests.
It is responsible for storage, retrieval, and performing checks
when writing authenticated variables.


%package tools
Summary: Tools for manipulating a guest's EFI variables offline


%description tools
Provides a set of tools for manipulating a guest's EFI variables
when the guest is not running.


%prep
%autosetup -p1
%{?_cov_prepare}


%build
%{?_cov_wrap} make %{?_smp_mflags} varstored tools PK.auth create-auth

%{?_cov_make_model:%{_cov_make_model misc/coverity/model.c}}


%install
install -m 755 -d %{buildroot}/%{_sbindir}
install -m 755 %{name} %{buildroot}/%{_sbindir}/%{name}
install -m 755 -d %{buildroot}/%{_bindir}
install -m 755 tools/varstore-{ls,get,rm,set,sb-state} %{buildroot}/%{_bindir}
install -m 755 -d %{buildroot}/%{_datadir}/%{name}
install -m 644 PK.auth %{buildroot}/%{_datadir}/%{name}
mkdir -p %{buildroot}/opt/xensource/libexec/
install -m 755 create-auth %{buildroot}/opt/xensource/libexec/create-auth

%{?_cov_install}


%check
make check


%files
%license LICENSE
%{_sbindir}/*
%{_datadir}/%{name}


%files tools
%license LICENSE
%{_bindir}/*
/opt/xensource/libexec/create-auth

%{?_cov_results_package}


%changelog
* Mon Mar 07 2022 Ross Lagerwall <ross.lagerwall@citrix.com> - 1.0.0-2
- Correct license field

* Fri Jun 25 2021 Ross Lagerwall <ross.lagerwall@citrix.com> - 1.0.0-1
- Switch upstream to GitHub

* Mon Mar 15 2021 Andrew Cooper <andrew.cooper3@citrix.com> - 0.9.5-1
- Switch to using stable Xen hypercalls only
- Don't configure bufioreq facilities
- Correct memory barriers

* Tue Mar 09 2021 Ross Lagerwall <ross.lagerwall@citrix.com> - 0.9.4-1
- CA-352332: Skip setting PK if KEK/db are missing

* Tue Feb 02 2021 Ross Lagerwall <ross.lagerwall@citrix.com> - 0.9.3-1
- CP-35896: varstore-get: Handle bad data_len
- CP-35896: Check count of variables before looping
- CP-35896: Check the return value of ASN1_get_object
- CP-35896: Initialize digest to zero
- CP-35896: Fix loading the certificate digest from serialized state
- CA-351587: Move crypto initialization earlier

* Wed Jan 27 2021 Ross Lagerwall <ross.lagerwall@citrix.com> - 0.9.2-1
- CA-351037: Use CC in the Makefile
- CA-351037: Fix issues reported by clang scan-build
- CP-35896: Add Coverity model and static analysis config
- CP-35896: Fix issues reported by Coverity

* Wed Jun 24 2020 Ross Lagerwall <ross.lagerwall@citrix.com> - 0.9.1-1
- CA-341597: Handle SIGTERM before the main loop is running
- CA-341597: Fix error message

* Mon Apr 20 2020 Ross Lagerwall <ross.lagerwall@citrix.com> - 0.9.0-1
- CA-333946: Make user mode == deployed mode
- CA-333944: Increase total size of variable storage to 128 KiB
- CA-333944: Set SignatureOwner to Microsoft's GUID for KEK and db

* Thu Sep 26 2019 Ross Lagerwall <ross.lagerwall@citrix.com> - 0.8.1-1
- CP-32192: Use func rather than offset to access EVP_PKEY

* Mon Jul 01 2019 Ross Lagerwall <ross.lagerwall@citrix.com> - 0.8.0-1
- Add a comment for commit a86b34eeac45
- Don't make auth target by default
- Cleanup initialize_settings()
- CA-322067: Use new resource mapping API

* Wed May 29 2019 Edwin Török <edvin.torok@citrix.com> - 0.7.0-1
- CP-30435 read feature flag in varstored to determine state of bootmode
- CP-30582 reverse setup keys
- Fix for CA-312835 and extra logging
- Add unit test for CA-312835

* Thu Feb 21 2019 Patrick Fox <patrick.fox@citrix.com> - 0.6.0-3
- Depend on SecureBoot Certificates Script for storing certificates in XAPI
- Build create-auth

* Fri Nov 23 2018 Edwin Török <edvin.torok@citrix.com> - 0.6.0-2
- Depend on varstored-guard for deprivileged operations

* Fri Nov 16 2018 Ross Lagerwall <ross.lagerwall@citrix.com> - 0.5.0-1
- Bump version to v0.5.0 since varstored is now functionally complete.

* Fri May 18 2018 Ross Lagerwall <ross.lagerwall@citrix.com> - 0.1.0-1
- Initial packaging