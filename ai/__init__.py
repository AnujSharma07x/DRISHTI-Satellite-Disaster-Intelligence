"""
DRISHTI - AI Flood Detection Module (Engineer 2)

Owns exactly this slice of the pipeline (ARCHITECTURE.md System Diagram):

    Satellite data -> Preprocessing -> AI flood detection -> Flood mask
                                                             -> Flood polygon
                                                             -> Flood statistics

Writes to `flood_predictions` are performed by Engineer 1's integration
layer, not by this package. See README.md for the full contract and how to
run this module independently.
"""

__version__ = "0.1.0"
