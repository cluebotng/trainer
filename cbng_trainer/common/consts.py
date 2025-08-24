FALSE_POSITIVES_PLOT = """
set terminal png
set output 'falsepositives.png'

set title 'Vandalism Detection Rate by False Positives'
set xlabel 'False Positive Rate'
set ylabel 'Portion of Vandalism'
set xrange [0.0:0.02]
set grid

plot 'thresholdtable.txt' using 3:2 title 'Vandalism Detection Rate' with lines
"""  #  noqa

THREASHOLDS_PLOT = """
set terminal png
set output 'thresholds.png'

set title 'Detection Rates By Threshold'
set xlabel 'Score Vandalism Threshold'
set ylabel 'Detection Rate'

plot 'thresholdtable.txt' using 1:2 title 'Correct Positive %' with lines, 'thresholdtable.txt' using 1:3 title 'False Positive %' with lines
"""  #  noqa

JOB_LOGS_END_MARKER = "## JOB FINISHED MARKER ##"
