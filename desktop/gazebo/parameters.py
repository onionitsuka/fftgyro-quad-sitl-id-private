def common_parameters(artifact: dict) -> dict[str, float]:
    """PX4 allocation matches the physical model's motor numbering and geometry."""
    c = artifact["settings"]
    a = c["arm_xy_m"]
    # Shared conservative PX4 gains for the measured 50-ms motor-command delay.
    # These are frozen for all routes, not stock X500 gains or a per-model retune.
    result = dict(MPC_THR_HOVER=.427, MAV_0_BROADCAST=0, MAV_1_BROADCAST=0,
                  MC_ROLL_P=3., MC_PITCH_P=3., MC_YAW_P=2.,
                  MC_ROLLRATE_P=.06, MC_PITCHRATE_P=.06, MC_YAWRATE_P=.1,
                  MC_ROLLRATE_I=.05, MC_PITCHRATE_I=.05, MC_YAWRATE_I=.03,
                  MC_ROLLRATE_D=.001, MC_PITCHRATE_D=.001)
    # PX4 ControlAllocator zeros an axis if every effectiveness entry <= .05.
    # CT=1 with measured KM~=0.019 silently removed yaw authority. Retain the
    # stock X500 CT=6.5 allocation scale (not the physical thrust coefficient).
    # Common scaling cancels in normalized allocation; KM=KQ/KF stays measured.
    allocation_ct = 6.5
    if allocation_ct * abs(c["kq"] / c["kf"]) <= .05:
        raise ValueError("PX4 allocation yaw authority below its .05 threshold")
    for j, (x, y, spin) in enumerate(zip((a, -a, a, -a), (a, -a, -a, a), (1, 1, -1, -1), strict=True)):
        result.update({f"CA_ROTOR{j}_PX": x, f"CA_ROTOR{j}_PY": y,
                       f"CA_ROTOR{j}_KM": spin * c["kq"] / c["kf"], f"CA_ROTOR{j}_CT": allocation_ct})
    return result
