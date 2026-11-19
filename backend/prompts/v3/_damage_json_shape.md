Return ONLY a valid JSON object ("damages" is an empty array if nothing is damaged):
{
  "damages": [
    {
      "component": "<component_name>",
      "damage_type": "<scratch|dent|crack|shatter|crush|deformation|missing>",
      "severity": 0.0,
      "description": "<brief description>"
    }
  ]
}
