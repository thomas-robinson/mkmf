"""
Unit tests for mkcf - CMakeLists.txt generator.

These tests verify that mkcf correctly:
1. Parses command-line arguments
2. Scans source files for dependencies
3. Parses mkmf template files
4. Generates valid CMakeLists.txt content
5. Handles the --use-cpp option for Fortran preprocessing

Run tests with:
    pytest t/test_mkcf.py -v

Run with coverage:
    pytest t/test_mkcf.py -v --cov=bin/mkcf --cov-report=html
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add bin directory to path so we can import mkcf
bin_dir = Path(__file__).resolve().parent.parent / "bin"
sys.path.insert(0, str(bin_dir))

# Import mkcf module components
# We need to use importlib since mkcf doesn't have .py extension
import importlib.util

mkcf_path = bin_dir / "mkcf"

# Load the module
spec = importlib.util.spec_from_loader(
    "mkcf",
    importlib.machinery.SourceFileLoader("mkcf", str(mkcf_path))
)
mkcf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mkcf)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_fortran_source(temp_dir):
    """Create a sample Fortran source file with module definitions."""
    source_content = """\
module test_mod
  implicit none
contains
  subroutine test_sub()
    print *, "Hello from test_mod"
  end subroutine test_sub
end module test_mod
"""
    source_file = temp_dir / "test_mod.F90"
    source_file.write_text(source_content)
    return source_file


@pytest.fixture
def sample_fortran_with_use(temp_dir):
    """Create a Fortran source file that uses another module."""
    source_content = """\
program main
  use test_mod
  use iso_c_binding
  implicit none
#include "header.h"
  call test_sub()
end program main
"""
    source_file = temp_dir / "main.F90"
    source_file.write_text(source_content)
    return source_file


@pytest.fixture
def sample_c_source(temp_dir):
    """Create a sample C source file."""
    source_content = """\
#include <stdio.h>
#include "myheader.h"

int my_function() {
    printf("Hello from C\\n");
    return 0;
}
"""
    source_file = temp_dir / "mycode.c"
    source_file.write_text(source_content)
    return source_file


@pytest.fixture
def sample_template(temp_dir):
    """Create a sample mkmf template file."""
    template_content = """\
# Sample mkmf template for testing
FC = gfortran
CC = gcc
CXX = g++
LD = gfortran

FFLAGS := -fdefault-real-8 -ffree-line-length-none
FFLAGS_OPT = -O3
FFLAGS_REPRO = -O2
FFLAGS_DEBUG = -O0 -g -fbounds-check
FFLAGS_OPENMP = -fopenmp

CFLAGS := -D__IFC
CFLAGS_OPT = -O2
CFLAGS_REPRO = -O2
CFLAGS_DEBUG = -O0 -g
CFLAGS_OPENMP = -fopenmp

CPPFLAGS := -D__TESTING
LDFLAGS := -L/usr/lib
LDFLAGS_OPENMP := -fopenmp
LIBS := -lnetcdf
"""
    template_file = temp_dir / "test_template.mk"
    template_file.write_text(template_content)
    return template_file


@pytest.fixture
def sample_pathnames_file(temp_dir, sample_fortran_source, sample_c_source):
    """Create a pathnames file listing source files."""
    pathnames_content = f"""\
{sample_fortran_source}
{sample_c_source}
"""
    pathnames_file = temp_dir / "path_names"
    pathnames_file.write_text(pathnames_content)
    return pathnames_file


@pytest.fixture
def sample_submodule_source(temp_dir):
    """Create a Fortran source file with submodule definition."""
    source_content = """\
submodule (parent_mod) child_mod
  implicit none
contains
  module subroutine child_sub()
    print *, "Hello from submodule"
  end subroutine child_sub
end submodule child_mod
"""
    source_file = temp_dir / "child_mod.F90"
    source_file.write_text(source_content)
    return source_file


# =============================================================================
# Tests for Source File Scanning
# =============================================================================


class TestSourceFileScanning:
    """Tests for scanning source files for dependencies."""

    def test_get_suffix_fortran_uppercase(self, temp_dir):
        """Test that .F90 suffix is detected correctly."""
        file_path = temp_dir / "test.F90"
        file_path.touch()
        suffix = mkcf.get_suffix(file_path)
        assert suffix == ".F90"

    def test_get_suffix_fortran_lowercase(self, temp_dir):
        """Test that .f90 suffix is detected correctly."""
        file_path = temp_dir / "test.f90"
        file_path.touch()
        suffix = mkcf.get_suffix(file_path)
        assert suffix == ".f90"

    def test_get_suffix_c(self, temp_dir):
        """Test that .c suffix is detected correctly."""
        file_path = temp_dir / "test.c"
        file_path.touch()
        suffix = mkcf.get_suffix(file_path)
        assert suffix == ".c"

    def test_is_source_file_positive(self, temp_dir):
        """Test is_source_file returns True for source files."""
        for suffix in [".F90", ".f90", ".F", ".f", ".c", ".C", ".cpp"]:
            file_path = temp_dir / f"test{suffix}"
            file_path.touch()
            assert mkcf.is_source_file(file_path), f"Failed for {suffix}"

    def test_is_source_file_negative(self, temp_dir):
        """Test is_source_file returns False for non-source files."""
        for suffix in [".txt", ".md", ".h"]:
            file_path = temp_dir / f"test{suffix}"
            file_path.touch()
            assert not mkcf.is_source_file(file_path), f"Failed for {suffix}"

    def test_is_include_file(self, temp_dir):
        """Test is_include_file returns True for include files."""
        for suffix in [".h", ".H", ".inc", ".fh"]:
            file_path = temp_dir / f"test{suffix}"
            file_path.touch()
            assert mkcf.is_include_file(file_path), f"Failed for {suffix}"

    def test_scan_file_finds_module_definition(self, sample_fortran_source):
        """Test that module definitions are found."""
        source = mkcf.scan_file_for_dependencies(sample_fortran_source)
        assert "test_mod" in source.modules_defined

    def test_scan_file_finds_use_statement(self, sample_fortran_with_use):
        """Test that use statements are found."""
        source = mkcf.scan_file_for_dependencies(sample_fortran_with_use)
        assert "test_mod" in source.modules_used
        assert "iso_c_binding" in source.modules_used

    def test_scan_file_finds_includes(self, sample_fortran_with_use):
        """Test that include statements are found."""
        source = mkcf.scan_file_for_dependencies(sample_fortran_with_use)
        assert "header.h" in source.includes

    def test_scan_file_c_includes(self, sample_c_source):
        """Test that C include statements are found."""
        source = mkcf.scan_file_for_dependencies(sample_c_source)
        assert "stdio.h" in source.includes
        assert "myheader.h" in source.includes

    def test_scan_file_sets_requires_cpp(self, sample_fortran_source):
        """Test that .F90 files are marked as requiring CPP."""
        source = mkcf.scan_file_for_dependencies(sample_fortran_source)
        assert source.requires_cpp is True

    def test_scan_file_f90_no_cpp(self, temp_dir):
        """Test that .f90 files are not marked as requiring CPP."""
        source_file = temp_dir / "test.f90"
        source_file.write_text("program test\nend program test\n")
        source = mkcf.scan_file_for_dependencies(source_file)
        assert source.requires_cpp is False

    def test_scan_file_submodule(self, sample_submodule_source):
        """Test that submodule parent dependencies are found."""
        source = mkcf.scan_file_for_dependencies(sample_submodule_source)
        assert "parent_mod" in source.modules_used

    def test_scan_file_ignores_module_subroutine(self, temp_dir):
        """Test that 'module subroutine' is not treated as module definition."""
        source_content = """\
module real_mod
contains
  module subroutine my_sub()
  end subroutine my_sub
  module function my_func()
  end function my_func
  module procedure my_proc
end module real_mod
"""
        source_file = temp_dir / "test.F90"
        source_file.write_text(source_content)
        source = mkcf.scan_file_for_dependencies(source_file)
        # Should only find 'real_mod', not 'subroutine', 'function', or 'procedure'
        assert source.modules_defined == ["real_mod"]


# =============================================================================
# Tests for Template Parsing
# =============================================================================


class TestTemplateParsing:
    """Tests for parsing mkmf template files."""

    def test_parse_template_compilers(self, sample_template):
        """Test that compiler commands are parsed correctly."""
        config = mkcf.parse_template(sample_template)
        assert config.fc == "gfortran"
        assert config.cc == "gcc"
        assert config.cxx == "g++"
        assert config.ld == "gfortran"

    def test_parse_template_fflags(self, sample_template):
        """Test that Fortran flags are parsed correctly."""
        config = mkcf.parse_template(sample_template)
        assert "-fdefault-real-8" in config.fflags_base
        assert config.fflags_opt == "-O3"
        assert config.fflags_repro == "-O2"
        assert "-g" in config.fflags_debug
        assert config.fflags_openmp == "-fopenmp"

    def test_parse_template_cflags(self, sample_template):
        """Test that C flags are parsed correctly."""
        config = mkcf.parse_template(sample_template)
        assert config.cflags_opt == "-O2"
        assert config.cflags_debug == "-O0 -g"
        assert config.cflags_openmp == "-fopenmp"

    def test_parse_template_ldflags(self, sample_template):
        """Test that linker flags are parsed correctly."""
        config = mkcf.parse_template(sample_template)
        assert "-L/usr/lib" in config.ldflags
        assert config.ldflags_openmp == "-fopenmp"

    def test_parse_template_libs(self, sample_template):
        """Test that libraries are parsed correctly."""
        config = mkcf.parse_template(sample_template)
        assert "-lnetcdf" in config.libs

    def test_parse_template_not_found(self, temp_dir):
        """Test that FileNotFoundError is raised for missing template."""
        with pytest.raises(FileNotFoundError):
            mkcf.parse_template(temp_dir / "nonexistent.mk")


# =============================================================================
# Tests for Source Collection
# =============================================================================


class TestSourceCollection:
    """Tests for collecting source files from targets."""

    def test_collect_from_directory(self, temp_dir, sample_fortran_source, sample_c_source):
        """Test collecting sources from a directory."""
        sources, inc_dirs = mkcf.collect_sources([str(temp_dir)])
        assert len(sources) >= 2
        source_names = [s.name for s in sources]
        assert "test_mod" in source_names
        assert "mycode" in source_names

    def test_collect_from_file(self, sample_fortran_source):
        """Test collecting a single source file."""
        sources, inc_dirs = mkcf.collect_sources([str(sample_fortran_source)])
        assert len(sources) == 1
        assert sources[0].name == "test_mod"

    def test_collect_from_pathnames(self, sample_pathnames_file):
        """Test collecting sources from a pathnames file."""
        sources, inc_dirs = mkcf.collect_sources([str(sample_pathnames_file)])
        assert len(sources) == 2

    def test_collect_with_abs_path(self, temp_dir, sample_fortran_source):
        """Test collecting sources with absolute path prefix."""
        # Create a relative path scenario
        rel_path = "src/test.F90"
        src_dir = temp_dir / "src"
        src_dir.mkdir()
        (src_dir / "test.F90").write_text("module test\nend module test\n")

        # Create pathnames file with relative path
        pathnames = temp_dir / "path_names"
        pathnames.write_text("src/test.F90\n")

        sources, inc_dirs = mkcf.collect_sources(
            [str(pathnames)], abs_path=temp_dir
        )
        assert len(sources) == 1

    def test_collect_avoids_duplicates(self, temp_dir):
        """Test that duplicate objects are avoided."""
        # Create two files that would produce the same object
        file1 = temp_dir / "subdir1" / "test.F90"
        file2 = temp_dir / "subdir2" / "test.F90"
        file1.parent.mkdir()
        file2.parent.mkdir()
        file1.write_text("module test1\nend module test1\n")
        file2.write_text("module test2\nend module test2\n")

        sources, _ = mkcf.collect_sources([
            str(temp_dir / "subdir1"),
            str(temp_dir / "subdir2")
        ])
        # Only one test.o should be included
        test_sources = [s for s in sources if s.name == "test"]
        assert len(test_sources) == 1


# =============================================================================
# Tests for CMakeLists.txt Generation
# =============================================================================


class TestCMakeGeneration:
    """Tests for generating CMakeLists.txt content."""

    def test_generate_basic_library(self, sample_fortran_source):
        """Test generating CMakeLists.txt for a basic library."""
        sources, inc_dirs = mkcf.collect_sources([str(sample_fortran_source)])
        cmake_content = mkcf.generate_cmakelists(
            sources=sources,
            include_dirs=inc_dirs,
            program_name="libtest.a",
            cppdefs="",
            other_flags="",
            link_flags="",
            template_config=None,
            src_root=None,
            build_root=None,
            use_cpp=False,
            verbose=False,
        )

        assert "cmake_minimum_required" in cmake_content
        assert "project(test LANGUAGES Fortran C)" in cmake_content
        assert "add_library(test STATIC" in cmake_content

    def test_generate_executable(self, sample_fortran_source):
        """Test generating CMakeLists.txt for an executable."""
        sources, inc_dirs = mkcf.collect_sources([str(sample_fortran_source)])
        cmake_content = mkcf.generate_cmakelists(
            sources=sources,
            include_dirs=inc_dirs,
            program_name="myprogram",
            cppdefs="",
            other_flags="",
            link_flags="",
            template_config=None,
            src_root=None,
            build_root=None,
            use_cpp=False,
            verbose=False,
        )

        assert "add_executable(myprogram" in cmake_content

    def test_generate_with_cppdefs(self, sample_fortran_source):
        """Test that CPP definitions are included."""
        sources, inc_dirs = mkcf.collect_sources([str(sample_fortran_source)])
        cmake_content = mkcf.generate_cmakelists(
            sources=sources,
            include_dirs=inc_dirs,
            program_name="libtest.a",
            cppdefs="-DUSE_NETCDF -DDEBUG",
            other_flags="",
            link_flags="",
            template_config=None,
            src_root=None,
            build_root=None,
            use_cpp=False,
            verbose=False,
        )

        assert "add_compile_definitions(USE_NETCDF)" in cmake_content
        assert "add_compile_definitions(DEBUG)" in cmake_content

    def test_generate_with_template(self, sample_fortran_source, sample_template):
        """Test generating with template configuration."""
        sources, inc_dirs = mkcf.collect_sources([str(sample_fortran_source)])
        template_config = mkcf.parse_template(sample_template)
        cmake_content = mkcf.generate_cmakelists(
            sources=sources,
            include_dirs=inc_dirs,
            program_name="libtest.a",
            cppdefs="",
            other_flags="",
            link_flags="",
            template_config=template_config,
            src_root=None,
            build_root=None,
            use_cpp=False,
            verbose=False,
        )

        assert 'FFLAGS_OPT' in cmake_content
        assert 'FFLAGS_DEBUG' in cmake_content
        assert 'FFLAGS_OPENMP' in cmake_content

    def test_generate_build_type_options(self, sample_fortran_source):
        """Test that build type options are generated."""
        sources, inc_dirs = mkcf.collect_sources([str(sample_fortran_source)])
        cmake_content = mkcf.generate_cmakelists(
            sources=sources,
            include_dirs=inc_dirs,
            program_name="libtest.a",
            cppdefs="",
            other_flags="",
            link_flags="",
            template_config=None,
            src_root=None,
            build_root=None,
            use_cpp=False,
            verbose=False,
        )

        assert 'option(PROD "Build with production/optimization flags" OFF)' in cmake_content
        assert 'option(REPRO "Build with reproducibility flags" OFF)' in cmake_content
        assert 'option(DEBUG_BUILD "Build with debug flags" OFF)' in cmake_content
        assert 'option(OPENMP "Enable OpenMP support" OFF)' in cmake_content
        assert 'set(NETCDF "" CACHE STRING "NetCDF version' in cmake_content

    def test_generate_with_use_cpp(self, sample_fortran_source):
        """Test that --use-cpp generates preprocessing rules."""
        sources, inc_dirs = mkcf.collect_sources([str(sample_fortran_source)])
        cmake_content = mkcf.generate_cmakelists(
            sources=sources,
            include_dirs=inc_dirs,
            program_name="libtest.a",
            cppdefs="",
            other_flags="",
            link_flags="",
            template_config=None,
            src_root=None,
            build_root=None,
            use_cpp=True,
            verbose=False,
        )

        assert 'option(USE_CPP "Use C preprocessor for .F90 files" ON)' in cmake_content
        assert "find_program(CPP_EXECUTABLE cpp)" in cmake_content
        assert "DO_NOT_MODIFY.f90" in cmake_content
        assert "add_custom_command" in cmake_content

    def test_generate_include_directories(self, temp_dir, sample_fortran_source):
        """Test that include directories are properly set."""
        inc_dir = temp_dir / "include"
        inc_dir.mkdir()
        (inc_dir / "test.h").touch()

        sources, inc_dirs = mkcf.collect_sources([str(sample_fortran_source)])
        inc_dirs.append(inc_dir)

        cmake_content = mkcf.generate_cmakelists(
            sources=sources,
            include_dirs=inc_dirs,
            program_name="libtest.a",
            cppdefs="",
            other_flags="",
            link_flags="",
            template_config=None,
            src_root=None,
            build_root=None,
            use_cpp=False,
            verbose=False,
        )

        assert "include_directories(" in cmake_content
        assert str(inc_dir) in cmake_content

    def test_generate_fortran_module_directory(self, sample_fortran_source):
        """Test that Fortran module directory is configured."""
        sources, inc_dirs = mkcf.collect_sources([str(sample_fortran_source)])
        cmake_content = mkcf.generate_cmakelists(
            sources=sources,
            include_dirs=inc_dirs,
            program_name="libtest.a",
            cppdefs="",
            other_flags="",
            link_flags="",
            template_config=None,
            src_root=None,
            build_root=None,
            use_cpp=False,
            verbose=False,
        )

        assert "CMAKE_Fortran_MODULE_DIRECTORY" in cmake_content

    def test_generate_mutual_exclusion_check(self, sample_fortran_source):
        """Test that mutual exclusion of build types is enforced."""
        sources, inc_dirs = mkcf.collect_sources([str(sample_fortran_source)])
        cmake_content = mkcf.generate_cmakelists(
            sources=sources,
            include_dirs=inc_dirs,
            program_name="libtest.a",
            cppdefs="",
            other_flags="",
            link_flags="",
            template_config=None,
            src_root=None,
            build_root=None,
            use_cpp=False,
            verbose=False,
        )

        assert "PROD, REPRO, DEBUG_BUILD, and TEST_BUILD are mutually exclusive" in cmake_content


# =============================================================================
# Tests for Clean Flags Function
# =============================================================================


class TestCleanFlags:
    """Tests for the clean_flags utility function."""

    def test_clean_simple_flags(self):
        """Test cleaning simple flags."""
        result = mkcf.clean_flags("-O3 -g")
        assert result == "-O3 -g"

    def test_clean_removes_make_variables(self):
        """Test that make variables are removed."""
        result = mkcf.clean_flags("$(INCLUDES) -O3 $(OTHER)")
        assert result == "-O3"

    def test_clean_handles_whitespace(self):
        """Test that excessive whitespace is normalized."""
        result = mkcf.clean_flags("  -O3    -g  ")
        assert result == "-O3 -g"


# =============================================================================
# Tests for CLI
# =============================================================================


class TestCLI:
    """Tests for the command-line interface."""

    def test_cli_help(self):
        """Test that --help works."""
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(mkcf.main, ["--help"])
        assert result.exit_code == 0
        assert "Generate CMakeLists.txt" in result.output

    def test_cli_version(self):
        """Test that --version works."""
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(mkcf.main, ["--version"])
        assert result.exit_code == 0
        assert mkcf.__version__ in result.output

    def test_cli_basic_run(self, temp_dir, sample_fortran_source):
        """Test basic CLI execution."""
        from click.testing import CliRunner

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(
                mkcf.main,
                ["-p", "libtest.a", str(sample_fortran_source)],
            )
            assert result.exit_code == 0
            assert Path("CMakeLists.txt").exists()

    def test_cli_with_template(self, temp_dir, sample_fortran_source, sample_template):
        """Test CLI with template file."""
        from click.testing import CliRunner

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(
                mkcf.main,
                [
                    "-t", str(sample_template),
                    "-p", "libtest.a",
                    str(sample_fortran_source),
                ],
            )
            assert result.exit_code == 0

    def test_cli_with_cppdefs(self, temp_dir, sample_fortran_source):
        """Test CLI with CPP definitions."""
        from click.testing import CliRunner

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(
                mkcf.main,
                [
                    "-c", "-DUSE_NETCDF -DDEBUG",
                    "-p", "libtest.a",
                    str(sample_fortran_source),
                ],
            )
            assert result.exit_code == 0
            cmake_content = Path("CMakeLists.txt").read_text()
            assert "USE_NETCDF" in cmake_content

    def test_cli_verbose(self, temp_dir, sample_fortran_source):
        """Test CLI verbose output."""
        from click.testing import CliRunner

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(
                mkcf.main,
                ["-v", "-p", "libtest.a", str(sample_fortran_source)],
            )
            assert result.exit_code == 0
            assert "mkcf" in result.output
            assert "Found" in result.output

    def test_cli_custom_output(self, temp_dir, sample_fortran_source):
        """Test CLI with custom output file name."""
        from click.testing import CliRunner

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(
                mkcf.main,
                [
                    "-m", "MyBuild.cmake",
                    "-p", "libtest.a",
                    str(sample_fortran_source),
                ],
            )
            assert result.exit_code == 0
            assert Path("MyBuild.cmake").exists()

    def test_cli_use_cpp(self, temp_dir, sample_fortran_source):
        """Test CLI with --use-cpp option."""
        from click.testing import CliRunner

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(
                mkcf.main,
                [
                    "--use-cpp",
                    "-p", "libtest.a",
                    str(sample_fortran_source),
                ],
            )
            assert result.exit_code == 0
            cmake_content = Path("CMakeLists.txt").read_text()
            assert "USE_CPP" in cmake_content

    def test_cli_include_directories(self, temp_dir, sample_fortran_source):
        """Test CLI with include directories."""
        from click.testing import CliRunner

        inc_dir = temp_dir / "include"
        inc_dir.mkdir()

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=str(temp_dir)):
            result = runner.invoke(
                mkcf.main,
                [
                    "-I", str(inc_dir),
                    "-p", "libtest.a",
                    str(sample_fortran_source),
                ],
            )
            assert result.exit_code == 0


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests that verify end-to-end functionality."""

    def test_full_workflow(self, temp_dir):
        """Test complete workflow from sources to CMakeLists.txt."""
        # Create a small project structure
        src_dir = temp_dir / "src"
        src_dir.mkdir()

        # Create module file
        (src_dir / "mymod.F90").write_text("""\
module mymod
  implicit none
  integer, parameter :: answer = 42
contains
  subroutine print_answer()
    print *, "The answer is", answer
  end subroutine print_answer
end module mymod
""")

        # Create main program
        (src_dir / "main.F90").write_text("""\
program main
  use mymod
  implicit none
  call print_answer()
end program main
""")

        # Collect and generate
        sources, inc_dirs = mkcf.collect_sources([str(src_dir)])
        cmake_content = mkcf.generate_cmakelists(
            sources=sources,
            include_dirs=inc_dirs,
            program_name="myprogram",
            cppdefs="-DDEBUG",
            other_flags="",
            link_flags="",
            template_config=None,
            src_root=src_dir,
            build_root=temp_dir / "build",
            use_cpp=False,
            verbose=False,
        )

        # Verify content
        assert "project(myprogram" in cmake_content
        assert "add_executable(myprogram" in cmake_content
        assert str(src_dir / "mymod.F90") in cmake_content
        assert str(src_dir / "main.F90") in cmake_content
        assert "add_compile_definitions(DEBUG)" in cmake_content
        assert "mymod <- mymod" in cmake_content  # Module comment

    def test_land_lad2_style_cpp(self, temp_dir):
        """Test --use-cpp workflow similar to land_lad2 build."""
        src_dir = temp_dir / "src"
        src_dir.mkdir()

        # Create preprocessed Fortran files
        (src_dir / "land_model.F90").write_text("""\
#ifdef INTERNAL_FILE_NML
module land_model
  implicit none
  character(len=256) :: input_nml_file = "input.nml"
#else
module land_model
  implicit none
#endif
contains
  subroutine init_land()
#ifdef DEBUG
    print *, "Debug mode enabled"
#endif
  end subroutine init_land
end module land_model
""")

        # Collect and generate with use_cpp
        sources, inc_dirs = mkcf.collect_sources([str(src_dir)])
        cmake_content = mkcf.generate_cmakelists(
            sources=sources,
            include_dirs=inc_dirs,
            program_name="libland_lad2.a",
            cppdefs="-DINTERNAL_FILE_NML -nostdinc",
            other_flags="",
            link_flags="",
            template_config=None,
            src_root=src_dir,
            build_root=temp_dir / "build",
            use_cpp=True,
            verbose=False,
        )

        # Verify preprocessing is set up
        assert "USE_CPP" in cmake_content
        assert "land_model.DO_NOT_MODIFY.f90" in cmake_content
        assert "cpp" in cmake_content.lower()
        assert "add_custom_command" in cmake_content


# =============================================================================
# Tests for Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_directory(self, temp_dir):
        """Test handling of empty directory."""
        empty_dir = temp_dir / "empty"
        empty_dir.mkdir()
        sources, inc_dirs = mkcf.collect_sources([str(empty_dir)])
        assert len(sources) == 0

    def test_nonexistent_file(self, temp_dir):
        """Test handling of nonexistent file in pathnames."""
        pathnames = temp_dir / "path_names"
        pathnames.write_text("/nonexistent/file.F90\n")
        sources, inc_dirs = mkcf.collect_sources([str(pathnames)])
        assert len(sources) == 0

    def test_file_with_read_error(self, temp_dir):
        """Test handling of files that can't be read."""
        # This tests the error handling in scan_file_for_dependencies
        source_file = temp_dir / "test.F90"
        source_file.write_bytes(b'\xff\xfe')  # Invalid UTF-8
        source = mkcf.scan_file_for_dependencies(source_file)
        # Should return source with no modules found, not crash
        assert source.name == "test"

    def test_cppdefs_with_values(self, sample_fortran_source):
        """Test CPP definitions with values."""
        sources, inc_dirs = mkcf.collect_sources([str(sample_fortran_source)])
        cmake_content = mkcf.generate_cmakelists(
            sources=sources,
            include_dirs=inc_dirs,
            program_name="libtest.a",
            cppdefs="-DVERSION=1.0 -DMAX_SIZE=100",
            other_flags="",
            link_flags="",
            template_config=None,
            src_root=None,
            build_root=None,
            use_cpp=False,
            verbose=False,
        )

        assert "add_compile_definitions(VERSION=1.0)" in cmake_content
        assert "add_compile_definitions(MAX_SIZE=100)" in cmake_content

    def test_other_flags_with_includes(self, temp_dir, sample_fortran_source):
        """Test that -I flags in other_flags are extracted."""
        inc_dir = temp_dir / "custom_include"
        inc_dir.mkdir()

        sources, inc_dirs = mkcf.collect_sources([str(sample_fortran_source)])
        cmake_content = mkcf.generate_cmakelists(
            sources=sources,
            include_dirs=inc_dirs,
            program_name="libtest.a",
            cppdefs="",
            other_flags=f"-I{inc_dir} -Wall",
            link_flags="",
            template_config=None,
            src_root=None,
            build_root=None,
            use_cpp=False,
            verbose=False,
        )

        assert "-Wall" in cmake_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
