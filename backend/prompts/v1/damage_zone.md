Carefully examine these vehicle images and focus ONLY on the ${zone_upper} ZONE.
Look specifically for damage on these components: [${component_list}].
Ignore all other parts of the vehicle.

For each damaged component from the list above, provide:
- component: exact name from [${component_list}]
- damage_type: one of [scratch, dent, crack, shatter, crush, deformation, missing]
- ${severity_guide}
- description: brief description of the specific damage you observe

If none of these components are damaged, return an empty array.

${damage_json_shape}
