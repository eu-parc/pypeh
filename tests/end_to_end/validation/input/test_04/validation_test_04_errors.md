# Test 04 - Errors included:

## SAMPLE

- Id_sample 1 has a sampling date later than the analysis day. 
- Id_sample 31 has a sampling hour that does not exist,
- Id_sample 1259 has sampling minutes but not sampling hour.
- Id_sample 254 has an impossible sampling date (Feb 30th)
- Id_sample 284 does not have timepoint. 
- Participant 222E has an invalid id_subject value (string instead of numeric).

## SUBJECTUNIQUE

- Subject 24 does not have any relation value
- Participant 18 has a mother whose age at birth is incorrect (2years old)
- Participant 222E has an invalid id_subject value (string instead of numeric).

## SUBJECTTIMEPOINT

- Subject 1 has incorrect format for variable nuts2
- Subject 27 has nuts2 and nuts3 but not nuts1
- Row 8 does not have id_subject
- Subject 10 has country UK - this country does not correspond to the nuts values
- Participant 20 has wrong nuts2 value (It should be the same as nuts 3 value minus the last character). 
- Participant 93 has incorrect degurba value.
- Participant 83 has ageyears not consistent with agemonths.
- Participant 101 age should be flagged as it is out of range.
- Participant 8: isced and isced raw values do not coincide. 
- Participant 5 has isced_m_raw value out of categories. 
- Participant 14 is missing isced_f while isceD_f_raw is available. 
- Participant 3: isced_hh_raw is not correctly calculated
- Participant 5: isced_hh is not correctly calculated/
- Participant 13: smoking has incorrect value.
- Participant 6: height should be flagged. 
- Participant 21: bmi incorrectly calculated

## SAMPLETIMEPOINT_BWB

- Id 860 chol value is too high
- Id 866 trigl value is too high
- Id 867 lipid value is too high
- Id 870 ag value is not correctly substituted (< LOD, should be -1)
- Id 862 is not correctly substituted (should be -2)
- Id 883 has MO value with incorrect format.
