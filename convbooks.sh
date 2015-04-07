#!/bin/bash - 
set -o nounset                              # Treat unset variables as an error

COVER_DIR1=$HOME/my/book/covers
COVER_DIR2=$HOME/ebooks/covers

function EchoUsage()
{
    echo "
    Usage: ${0##*/} [options] <book> [<book> <book> ...]

      Options:

          -d, --dest path    : Destination directory, default to current directory
          -h, --help         : show this screen
          -p, --plain-toc    : plain TOC
          -P, --no-plain-toc : no plain TOC
              --toc          : Generate inline TOC
              --no-toc       : Don't generate inline TOC
          -c, --cover file   : Cover
          -C, --category cat : Category
          -O, --offline      : Don't fetch book info from internet
          -v, --verbose      : Verbose
          -b, --skip-bad-img : Ignore and skip bad images
" >&2
}

TEMP=`getopt -o hd:pPc:C:Ovb --long help,dest:,plain-toc,no-plain-toc,no-toc,cover:,category:,offline,verbose,skip-bad-img -- "$@"`

if [ $? != 0 ] ; then echo "Terminating..." >&2 ; exit 1 ; fi

# Note the quotes around `$TEMP': they are essential!
eval set -- "$TEMP"

global_switches=
dest=
cover=
plainToc=
toc=--no-toc

while true ; do
	case "$1" in
		-h|--help)
            EchoUsage
            exit 1
            ;;
        -b|--skip-bad-img)
            global_switches="${global_switches} --skip-bad-img"
            shift 1
            ;;
        -d|--dest)
            dest="$2"
            shift 2
            ;;
        -p|--plain-toc)
            plainToc=--plain-toc
            shift 1
            ;;
        -P|--no-plain-toc)
            plainToc=
            shift 1
            ;;
        --toc)
            toc=
            shift 1
            ;;
        --no-toc)
            toc=--no-toc
            shift 1
            ;;
        -c|--cover)
            cover="$2"
            shift 2
            ;;
        -C|--category)
            global_switches="${global_switches} --category \"$2\""
            shift 2
            ;;
        -O|--offline)
            global_switches="${global_switches} --offline"
            shift 1
            ;;
        -v|--verbose)
            global_switches="${global_switches} --verbose"
            shift 1
            ;;
		--)
            shift
            break
            ;;
		*) 
            echo "Internal error!"
            exit 1
            ;;
	esac
done

if [ $# -le 0 ]
then
    EchoUsage
    exit 1
fi

global_switches="${global_switches} ${plainToc} ${toc}"

for book
do
    bookconv_switches="${global_switches}"

    ext="${book##*.}"
    name="${book%.$ext}"

    lowerExt="$(echo -n "${ext}" | tr [:upper:] [:lower:])"

    case "$lowerExt" in
        txt|chm|asciidoc)
            ;;
        *)
            echo "Skip '${book}'"
            continue
            ;;
    esac

    output=.
    #if [ ! -z "$dest" ]
    #then
    #    output="$dest/${name##*/}.epub"
    #else
    #    output="${name##*/}.epub"
    #fi
    if [ ! -z "$dest" ]
    then
        output="$dest/"
    fi
    
    if [ ! -z "$cover" ]
    then
        echo "Found cover '$cover'"
        bookconv_switches="${bookconv_switches} --cover \"${cover}\""
    fi

    eval "bookconv.py $bookconv_switches \"$book\" \"${output}\" ${bookconv_switches}"

    cover=
done

