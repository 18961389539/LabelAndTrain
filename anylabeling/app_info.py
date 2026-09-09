__appname__ = "JLLabelingAndTrain"
__appdescription__ = "Advanced Auto Labeling Solution with Added Features"
__version__ = "4.0.0-beta.14"
__url__ = "https://github.com/CVHub520/X-AnyLabeling"

CLI_HELP_MSG = """
    Usage: jllabelingandtrain [COMMAND] [OPTIONS]

    Available Commands:
        help              Show this help message
        checks            Display system and package information
        version           Show version information
        config            Show config file path
        convert           Run conversion tasks

    Launch Options:
        jllabelingandtrain                                    Launch the GUI application
        jllabelingandtrain --filename IMAGE                   Open specific image/folder
        jllabelingandtrain --output DIR                       Set output directory
        jllabelingandtrain --config FILE                      Use custom config file
        jllabelingandtrain --reset-config                     Reset Qt config
        jllabelingandtrain --qt-image-allocation-limit 1024  Set Qt image allocation limit to 1024 MB

    Conversion Tasks:
        jllabelingandtrain convert                            List all conversion tasks
        jllabelingandtrain convert --task <task>              Show help for a specific task
        jllabelingandtrain convert --task <task> [options]    Run conversion

    Examples:
        1. Launch the app:
            jllabelingandtrain

        2. Open an image:
            jllabelingandtrain --filename /path/to/image.jpg

        3. Check system information:
            jllabelingandtrain checks

        4. Show version:
            jllabelingandtrain version

        5. List all conversion tasks:
            jllabelingandtrain convert

        6. Show help for a conversion task:
            jllabelingandtrain convert --task yolo2xlabel

        7. Convert YOLO to XLABEL:
            jllabelingandtrain convert --task yolo2xlabel --mode detect --images ./images --labels ./labels --output ./output --classes classes.txt

    For more options, use: jllabelingandtrain --help

    Docs: https://github.com/CVHub520/X-AnyLabeling/tree/main/docs
    Examples: https://github.com/CVHub520/X-AnyLabeling/tree/main/examples/
    GitHub: https://github.com/CVHub520/X-AnyLabeling
"""


def __getattr__(name):
    if name == "__preferred_device__":
        from anylabeling.views.common.device_manager import (
            get_preferred_device,
        )

        return get_preferred_device()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
