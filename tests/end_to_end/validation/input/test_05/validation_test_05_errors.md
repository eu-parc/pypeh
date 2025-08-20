# Test 05 - Errors included:

## SUBJECTUNIQUE

- Participant 7 has value 1 for case_control but no one else does. This should be flagged.

## SUBJECTTIMEPOINT

- Subject 9 has population value 4 while everyone else has population value 1  this should be flagged.
- Subject 10 has country UK.  flagged because all other participants have country value BE

## SAMPLETIMEPOINT_BWB

- Id 873 ag_lod should be flagged as it is different as all the rest of the values.
- Id 863 cu should be flagged as value is very high compared to the rest.
