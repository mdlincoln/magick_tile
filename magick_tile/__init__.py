import subprocess


def is_magick_installed() -> bool:
    """
    Confirm that Imagemagick is installed and on $PATH
    """
    try:
        subprocess.run(["convert", "--version"], stdout=subprocess.PIPE)
        return True
    except:
        return False


if not is_magick_installed():
    raise Exception(
        "ImageMagick's 'convert' does not appear to be installed or available on your $PATH"
    )
