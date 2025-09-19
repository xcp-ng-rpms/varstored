#!/usr/bin/env python3

# Implementation of Secure Boot variable generation.
# Uses the dbx schema from https://github.com/microsoft/secureboot_objects.
# Note that this script could be used to generate PK/KEK/db and not just dbx,
# depending on the ESL sets chosen.

# SPDX-License-Identifier: BSD-2-Clause

import argparse
import datetime
import json
import logging
import pathlib
import struct
import subprocess
import tempfile
import typing
import uuid


"""Map from RPM arch to microsoft/secureboot_objects arch"""
SUPPORTED_ARCHITECTURES = {
    "x86_64": "x64",
}

EFI_CERT_X509_GUID = uuid.UUID("a5c059a1-94e4-4aa7-87b5-ab155c2bf072")
EFI_CERT_SHA256_GUID = uuid.UUID("c1c41626-504c-4092-aca9-41f936934328")

EFI_SIGNATURE_LIST = struct.Struct("<16sIII")

SVN_OWNER_GUID = uuid.UUID("9d132b6c-59d5-4388-ab1c-185cfcb2eb92")

EFI_VARIABLE_NON_VOLATILE = 0x00000001
EFI_VARIABLE_BOOTSERVICE_ACCESS = 0x00000002
EFI_VARIABLE_RUNTIME_ACCESS = 0x00000004
EFI_VARIABLE_TIME_BASED_AUTHENTICATED_WRITE_ACCESS = 0x00000020
EFI_VARIABLE_APPEND_WRITE = 0x00000040

EFI_TIME = struct.Struct("<HBBBBBBIhBB")
assert EFI_TIME.size == 16
EFI_TIME_APPEND = EFI_TIME.pack(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

WIN_CERTIFICATE_UEFI_GUID = struct.Struct("<IHH16s")
EFI_CERT_TYPE_PKCS7_GUID = uuid.UUID("4aafd29d-68df-49ee-8aa9-347d375665a7")
WIN_CERT_TYPE_EFI_GUID = 0x0EF1

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def parse_timestamp(s: str):
    return datetime.datetime.strptime(s, TIMESTAMP_FORMAT)


def make_efi_signature_data_sha256(owner: uuid.UUID, hash: bytes):
    assert len(hash) == 32
    return owner.bytes_le + hash


def make_efi_signature_data_x509(owner: uuid.UUID, cert_bytes: bytes):
    assert cert_bytes
    return owner.bytes_le + cert_bytes


def make_efi_signature_list(type: uuid.UUID, signatures: typing.List[bytes]):
    siglen = len(signatures[0])
    logging.info(f"siglen {siglen}")
    if not all(map(lambda s: len(s) == siglen, signatures)):
        raise RuntimeError("Invalid signature list")
    header = EFI_SIGNATURE_LIST.pack(
        type.bytes_le,  # signature type
        EFI_SIGNATURE_LIST.size + siglen * len(signatures),  # signature list size
        0,  # signature header size
        siglen,  # signature size
    )
    siglist = b"".join([header] + signatures)
    logging.info(f"siglist len {len(siglist)}")
    return siglist


def make_efi_time(time: datetime.datetime, authvar: bool, append: bool):
    if append:
        # use special timestamp as specified
        return EFI_TIME_APPEND
    else:
        return EFI_TIME.pack(
            time.year,  # Year
            time.month,  # Month
            time.day,  # Day
            time.hour,  # Hour
            time.minute,  # Minute
            time.second,  # Second
            0,  # Pad1
            0 if authvar else time.microsecond * 1000,  # Nanosecond
            0,  # TimeZone
            0,  # Daylight
            0,  # Pad2
        )


def make_efi_auth_variable(
    varname: str,
    varguid: uuid.UUID,
    siglists: typing.List[bytes],
    timestamp: datetime.datetime,
    attributes: int,
    append: bool,
    signer_cert: typing.Union[str, pathlib.Path, None],
    signer_key: typing.Union[str, pathlib.Path, None],
    tmpdir: str,
):
    timestamp_bytes = make_efi_time(timestamp, authvar=True, append=append)

    siglists_bytes = b"".join(siglists)
    logging.info(f"total siglist {len(siglists_bytes)} bytes")

    attributes = attributes | (EFI_VARIABLE_APPEND_WRITE if append else 0)
    logging.info(f"attributes 0x{attributes:x}")
    signable = b"".join(
        [
            varname.encode("utf-16le"),
            varguid.bytes_le,
            struct.pack("<I", attributes),
            timestamp_bytes,
            siglists_bytes,
        ]
    )

    signature = b""
    if signer_cert and signer_key:
        with tempfile.NamedTemporaryFile(
            dir=pathlib.Path(tmpdir), delete=False
        ) as signable_file, tempfile.NamedTemporaryFile(dir=pathlib.Path(tmpdir), delete=False) as signature_file:
            signable_file.write(signable)
            signable_file.close()

            signature_file.close()
            subprocess.run(
                [
                    "openssl",
                    "smime",
                    "-sign",
                    "-in",
                    signable_file.name,
                    "-out",
                    signature_file.name,
                    "-outform",
                    "DER",
                    "-signer",
                    str(signer_cert),
                    "-inkey",
                    str(signer_key),
                    "-md",
                    "SHA256",
                    "-noattr",
                    "-binary",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            signature = pathlib.Path(signature_file.name).read_bytes()
    elif signer_cert or signer_key:
        raise ValueError("Signer cert and signer key must be provided together")

    authvar = b"".join(
        [
            timestamp_bytes,
            WIN_CERTIFICATE_UEFI_GUID.pack(
                WIN_CERTIFICATE_UEFI_GUID.size + len(signature),  # WIN_CERTIFICATE.dwLength
                0x0200,  # WIN_CERTIFICATE.wRevision
                WIN_CERT_TYPE_EFI_GUID,  # WIN_CERTIFICATE.wCertificateType
                EFI_CERT_TYPE_PKCS7_GUID.bytes_le,  # CertType
            ),
            signature,
            siglists_bytes,
        ]
    )

    return authvar, siglists_bytes, signable, signature


def convert_certificate(infile, outfile):
    logging.info(f"converting {infile} -> {outfile}")
    cert_forms = ["PEM", "DER"]
    for inform in cert_forms:
        logging.info(f"trying {inform}")
        try:
            subprocess.run(
                [
                    "openssl",
                    "x509",
                    "-in",
                    str(infile),
                    "-inform",
                    inform,
                    "-outform",
                    "DER",
                    "-out",
                    str(outfile),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            logging.info("OK")
            break
        except:
            pass
    else:
        raise Exception(f"Cannot convert certificate file {infile}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--architecture", required=True, choices=SUPPORTED_ARCHITECTURES.keys(), help="RPM architecture to build for"
    )
    parser.add_argument("--var-name", default="dbx", help="Authenticated variable name")
    parser.add_argument(
        "--var-guid", type=uuid.UUID, default="d719b2cb-3d3a-4596-a3bc-dad00e67656f", help="Authenticated variable name"
    )
    parser.add_argument(
        "--var-attributes",
        type=lambda x: int(x, base=0),
        default=str(
            EFI_VARIABLE_BOOTSERVICE_ACCESS
            | EFI_VARIABLE_RUNTIME_ACCESS
            | EFI_VARIABLE_NON_VOLATILE
            | EFI_VARIABLE_TIME_BASED_AUTHENTICATED_WRITE_ACCESS
        ),
        help="Authenticated variable attributes",
    )
    parser.add_argument("--input", required=True, type=argparse.FileType("r"), help="Input JSON file")
    parser.add_argument("--output", required=True, type=argparse.FileType("wb"), help="Output authenticated variable")
    parser.add_argument(
        "--sets",
        nargs="*",
        choices=["images", "certificates", "svns"],
        default=["images", "certificates", "svns"],
        help="DBX sets to process",
    )
    parser.add_argument("--signer-cert", type=pathlib.Path, help="Path of signer certificate")
    parser.add_argument("--signer-key", type=pathlib.Path, help="Path of signer private key")
    parser.add_argument("--cert-search-path", type=pathlib.Path, help="Root directory of certs specified in JSON")
    parser.add_argument("--vendor-guid", required=True, type=uuid.UUID, help="Vendor GUID for images and certs")
    parser.add_argument(
        "--timestamp",
        type=parse_timestamp,
        default=datetime.datetime.now(datetime.timezone.utc),
        help=f"Descriptor timestamp in the format {TIMESTAMP_FORMAT.replace('%', '%%')}",
    )
    parser.add_argument("--append", action="store_true", help="Appendable descriptor")
    parser.add_argument("--output-signable", type=argparse.FileType("wb"), help="Output signable file")
    parser.add_argument("--output-content", type=argparse.FileType("wb"), help="Output variable content file")
    parser.add_argument("--output-signature", type=argparse.FileType("wb"), help="Output signature file")
    args = parser.parse_args()

    logging.getLogger().setLevel(logging.INFO)

    rpm_arch = args.architecture
    data_arch = SUPPORTED_ARCHITECTURES[rpm_arch]
    sets = set(args.sets)

    with args.input as ifile, tempfile.TemporaryDirectory() as tmpdir:
        data = json.load(ifile)

        siglists = []

        if "images" in sets:
            siglist_images = []
            images: typing.List[dict] = data["images"][data_arch]
            for image in images:
                if image["hashType"] not in ["SHA256"]:
                    raise RuntimeError(f'Unsupported hash type {image["hashType"]}')
                if image.get("authenticodeHash"):
                    hash = bytes.fromhex(image.get("authenticodeHash"))
                    siglist_images.append(make_efi_signature_data_sha256(args.vendor_guid, hash))
                if image.get("flatHash"):
                    hash = bytes.fromhex(image.get("flatHash"))
                    siglist_images.append(make_efi_signature_data_sha256(args.vendor_guid, hash))
            if siglist_images:
                siglists.append(make_efi_signature_list(EFI_CERT_SHA256_GUID, siglist_images))

        if "certificates" in sets:
            certs: typing.List[dict] = data["certificates"]
            cert_path: pathlib.Path = args.cert_search_path or pathlib.Path.cwd()
            for cert in certs:
                cert_file_path = cert_path / cert["value"]
                with tempfile.NamedTemporaryFile(dir=pathlib.Path(tmpdir), delete=False) as cert_der:
                    cert_der.close()
                    convert_certificate(cert_file_path, cert_der.name)
                    cert_bytes = pathlib.Path(cert_der.name).read_bytes()
                    # each EFI_CERT_X509_GUID stays in its own EFI_SIGNATURE_DATA
                    cert_sigdata = make_efi_signature_data_x509(args.vendor_guid, cert_bytes)
                    siglists.append(
                        make_efi_signature_list(
                            EFI_CERT_X509_GUID,
                            [cert_sigdata],
                        )
                    )

        if "svns" in sets:
            siglist_svns = []
            svns: typing.List[dict] = data.get("svns", [])
            for svn in svns:
                hash = bytes.fromhex(svn.get("value"))
                siglist_svns.append(make_efi_signature_data_sha256(SVN_OWNER_GUID, hash))
            if siglist_svns:
                siglists.append(make_efi_signature_list(EFI_CERT_SHA256_GUID, siglist_svns))

        authvar, content, signable, signature = make_efi_auth_variable(
            varname=args.var_name,
            varguid=args.var_guid,
            siglists=siglists,
            timestamp=args.timestamp,
            attributes=args.var_attributes,
            append=args.append,
            signer_cert=args.signer_cert,
            signer_key=args.signer_key,
            tmpdir=tmpdir,
        )
        with args.output as ofile:
            ofile.write(authvar)

        if args.output_signable:
            with args.output_signable as sfile:
                sfile.write(signable)

        if args.output_content:
            with args.output_content as cfile:
                cfile.write(content)

        if args.output_signature:
            with args.output_signature as sigfile:
                sigfile.write(signature)
