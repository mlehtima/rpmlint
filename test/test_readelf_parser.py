import os

import pytest
from rpmlint.checks.BinariesCheck import BinariesCheck
from rpmlint.filter import Filter
from rpmlint.pkg import FakePkg, PkgFile
from rpmlint.readelfparser import ReadelfParser

from Testing import CONFIG, get_tested_path


@pytest.fixture(scope='function', autouse=True)
def binariescheck():
    CONFIG.info = True
    output = Filter(CONFIG)
    test = BinariesCheck(CONFIG, output)
    return output, test


def get_full_path(path):
    return str(get_tested_path(os.path.join('readelf', path)))


def readelfparser(path, system_path=None):
    if system_path is None:
        system_path = path
    return ReadelfParser(get_full_path(path), system_path)


def test_empty_archive():
    readelf = readelfparser('empty-archive.a')
    assert len(readelf.section_info.elf_files) == 0


def test_simple_archive():
    readelf = readelfparser('main.a')
    assert readelf.is_archive
    assert len(readelf.section_info.elf_files) == 1
    elf_file = readelf.section_info.elf_files[0]
    assert len(elf_file) == 11
    assert elf_file[0].name == '.text'
    assert elf_file[0].size == 21


def test_program_header_parsing():
    readelf = readelfparser('nested-function')
    assert len(readelf.program_header_info.headers) == 11
    h0 = readelf.program_header_info.headers[0]
    assert h0.name == 'PHDR'
    assert h0.flags == 'R'
    h9 = readelf.program_header_info.headers[9]
    assert h9.name == 'GNU_STACK'
    assert h9.flags == 'RWE'


def test_dynamic_section_parsing():
    readelf = readelfparser('libutil-2.29.so', '/lib64/libutil-2.29.so')
    assert readelf.is_shlib
    assert not readelf.is_archive
    sections = readelf.dynamic_section_info.sections
    assert len(sections) == 30
    assert sections[0].key == 'NEEDED'
    assert sections[0].value == 'Shared library: [libc.so.6]'
    assert readelf.dynamic_section_info['SYMTAB'] == ['0x4c8']
    assert readelf.dynamic_section_info['NULL'] == ['0x0']
    assert readelf.dynamic_section_info.soname == 'libutil.so.1'


def test_lto_bytecode(binariescheck):
    output, test = binariescheck
    test.run_elf_checks(FakePkg('fake'), get_full_path('lto-object.o'), 'x.a')
    assert not test.readelf_parser.parsing_failed()
    out = output.print_results(output.results)
    assert 'lto-bytecode' in out


def test_lto_archive_text(binariescheck):
    output, test = binariescheck
    test.run_elf_checks(FakePkg('fake'), get_full_path('stripped-lto.a'), 'x.a')
    assert len(output.results) == 1
    assert 'E: lto-no-text-in-archive' in output.results[0]


def test_lto_archive_text_function_sections(binariescheck):
    output, test = binariescheck
    test.run_elf_checks(FakePkg('fake'), get_full_path('function-sections.a'), 'x.a')
    assert len(output.results) == 0


def test_executable_stack(binariescheck):
    output, test = binariescheck
    test.run_elf_checks(FakePkg('fake'), get_full_path('executable-stack'), 'a.out')
    assert len(output.results) == 1
    assert 'E: executable-stack' in output.results[0]


def test_readelf_failure():
    readelf = readelfparser('no-existing-file')
    assert readelf.parsing_failed


def test_readelf_failure_in_package(binariescheck):
    output, test = binariescheck
    test.run_elf_checks(FakePkg('fake'), get_full_path('not-existing.so'), '/lib64/not-existing.so')
    out = output.print_results(output.results)
    assert 'binaryinfo-readelf-failed /lib64/not-existing.so' in out


def test_no_soname(binariescheck):
    output, test = binariescheck
    test.run_elf_checks(FakePkg('fake'), get_full_path('no-soname.so'), '/lib64/no-soname.so')
    out = output.print_results(output.results)
    assert 'no-soname /lib64/no-soname.so' in out


def test_invalid_soname(binariescheck):
    output, test = binariescheck
    test.run_elf_checks(FakePkg('fake'), get_full_path('invalid-soname.so'), '/lib64/invalid-soname.so')
    out = output.print_results(output.results)
    assert 'invalid-soname /lib64/invalid-soname.so' in out
    assert 'E: shlib-with-non-pic-code /lib64/invalid-soname.so' in out


def test_no_ldconfig_symlink(binariescheck):
    output, test = binariescheck

    test.run_elf_checks(FakePkg('fake'), get_full_path('libutil-2.29.so'), '/lib64/libutil-2.29.so')
    out = output.print_results(output.results)
    assert 'no-ldconfig-symlink /lib64/libutil-2.29.so' in out
    assert 'E: incoherent-version-in-name 1' in out


def test_invalid_ldconfig_symlink(binariescheck):
    output, test = binariescheck

    fakefile = PkgFile('/lib64/libutil.so.1')
    fakefile.linkto = '/lib64/libutil-bad.so'
    fakepkg = FakePkg('fake', [fakefile])

    test.run_elf_checks(fakepkg, get_full_path('libutil-2.29.so'), '/lib64/libutil-2.29.so')
    out = output.print_results(output.results)
    assert 'invalid-ldconfig-symlink /lib64/libutil-2.29.so' in out