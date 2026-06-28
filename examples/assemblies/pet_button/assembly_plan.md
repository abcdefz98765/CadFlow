# pet_button_assembly Assembly Plan

**Status:** ready_for_assembly_config
**Check level:** L0
**Risk level:** low

## Confirmation Gate

- Policy: pause_only_for_high_risk_topology
- Needs user confirmation: false
- High-risk topics: switch, wire_exit
- Question: None

## Parts

- pet_button_base: manufactured, role=base
- pet_button_switch_plate: manufactured, role=carrier
- pet_button_cap: manufactured, role=moving_actuator
- pet_button_tactile_switch: reference, role=switch_reference

## Placement Intent

- pet_button_base: Fixed base with electronics cavity, actuator window, and side wire outlet. (datum=bottom_z)
- pet_button_switch_plate: Switch carrier sits in the underside cavity and locates the tactile switch. (datum=bottom_z)
- pet_button_tactile_switch: Reference envelope for a 6x6 mm tactile switch and terminals. (datum=bottom_z)
- pet_button_cap: Moving cap enters the base recess and presses the switch stem through the actuator window. (datum=bottom_z)

## Required Contacts

- pet_button_switch_plate <-> pet_button_tactile_switch: tactile switch body is seated on the switch carrier

## Required Clearances

- pet_button_base <-> wire_harness: 0.5mm, wire outlet keeps routing clearance

## Allowed Overlaps

- pet_button_base <-> pet_button_cap: cap skirt and actuator stem intentionally enter the base recess and switch window
- pet_button_base <-> pet_button_switch_plate: switch carrier sits inside the underside electronics cavity
- pet_button_switch_plate <-> pet_button_tactile_switch: switch reference body sits in the carrier pocket
- pet_button_base <-> pet_button_tactile_switch: switch is mounted inside the base below the actuator window

## Serviceability

- Keep the tactile switch reachable until the design explicitly chooses a sealed assembly.
- Keep the wire exit direction and bend relief traceable in the assembly plan.
