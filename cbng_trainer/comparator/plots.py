'''
MIT License

Copyright (c) 2021 Damian Zaremba

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''
FALSE_POSITIVE = '''set terminal png
set output 'falsepositives.png'

set title 'Vandalism Detection Rate by False Positives'
set xlabel 'False Positive Rate'
set ylabel 'Portion of Vandalism'
set xrange [0.0:0.02]
set grid

plot 'thresholdtable.txt' using 3:2 title 'Vandalism Detection Rate' with lines
'''

THREASHOLD = '''set terminal png
set output 'thresholds.png'

set title 'Detection Rates By Threshold'
set xlabel 'Score Vandalism Threshold'
set ylabel 'Detection Rate'

plot 'thresholdtable.txt' using 1:2 title 'Correct Positive %' with lines, 'thresholdtable.txt' using 1:3 title 'False Positive %' with lines
'''
