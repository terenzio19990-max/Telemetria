# -*- coding: utf-8 -*-
"""Strutture di memoria dei giochi, scritte come in C.

Servono a due cose:
  1. genera_offset.py le usa per calcolare la posizione (offset) di ogni
     campo: il ponte legge i byte a quegli offset, senza dipendere da
     ctypes su ogni PC;
  2. le prove costruiscono memorie finte identiche a quelle dei giochi.

Fonti:
  - Assetto Corsa / ACC: documentazione Kunos "ACC Shared Memory" (struct
    SPageFilePhysics / SPageFileGraphic / SPageFileStatic) e sim_info.py
    delle app di AC.
  - AC EVO: documentazione Kunos ACE_SharedFileOut v1 (2026-04), trascritta
    in live-telemetry-evo/docs/SHARED_MEMORY.md.
  - AMS2: SharedMemory.h (Madness engine, versione 14) distribuito con il gioco.
  - Le Mans Ultimate: SharedMemoryInterface.hpp (S397) nella cartella
    Support\\SharedMemoryInterface del gioco.
  - rFactor 2: rF2State.h del plugin rF2SharedMemoryMapPlugin (The Iron Wolf).
Stringhe "wchar_t" di Windows = 2 byte: si usano array di c_uint16 perché
c_wchar su Linux vale 4 byte.
"""
import ctypes as C

i32, u32, f32, f64, u8, i8, i16, u16, u64, boo = (C.c_int32, C.c_uint32, C.c_float, C.c_double, C.c_uint8,
                                                  C.c_int8, C.c_int16, C.c_uint16, C.c_uint64, C.c_bool)
def W(n): return u16 * n          # wchar_t[n]
def S(n): return C.c_char * n     # char[n]


def struttura(nome, campi, pack=None):
    d = {'_fields_': campi}
    if pack:
        d['_pack_'] = pack
    return type(nome, (C.Structure,), d)


# ─────────────────────────── ASSETTO CORSA / ACC / EVO ───────────────────────────
AC_PHYSICS = struttura('ACPhysics', [
    ('packetId', i32), ('gas', f32), ('brake', f32), ('fuel', f32), ('gear', i32), ('rpms', i32),
    ('steerAngle', f32), ('speedKmh', f32), ('velocity', f32 * 3), ('accG', f32 * 3),
    ('wheelSlip', f32 * 4), ('wheelLoad', f32 * 4), ('wheelsPressure', f32 * 4), ('wheelAngularSpeed', f32 * 4),
    ('tyreWear', f32 * 4), ('tyreDirtyLevel', f32 * 4), ('tyreCoreTemperature', f32 * 4), ('camberRAD', f32 * 4),
    ('suspensionTravel', f32 * 4), ('drs', f32), ('tc', f32), ('heading', f32), ('pitch', f32), ('roll', f32),
    ('cgHeight', f32), ('carDamage', f32 * 5), ('numberOfTyresOut', i32), ('pitLimiterOn', i32), ('abs', f32),
    ('kersCharge', f32), ('kersInput', f32), ('autoShifterOn', i32), ('rideHeight', f32 * 2), ('turboBoost', f32),
    ('ballast', f32), ('airDensity', f32), ('airTemp', f32), ('roadTemp', f32), ('localAngularVel', f32 * 3),
    ('finalFF', f32), ('performanceMeter', f32), ('engineBrake', i32), ('ersRecoveryLevel', i32),
    ('ersPowerLevel', i32), ('ersHeatCharging', i32), ('ersIsCharging', i32), ('kersCurrentKJ', f32),
    ('drsAvailable', i32), ('drsEnabled', i32), ('brakeTemp', f32 * 4), ('clutch', f32),
    ('tyreTempI', f32 * 4), ('tyreTempM', f32 * 4), ('tyreTempO', f32 * 4), ('isAIControlled', i32),
    ('tyreContactPoint', f32 * 12), ('tyreContactNormal', f32 * 12), ('tyreContactHeading', f32 * 12),
    ('brakeBias', f32), ('localVelocity', f32 * 3), ('P2PActivations', i32), ('P2PStatus', i32),
    ('currentMaxRpm', i32), ('mz', f32 * 4), ('fx', f32 * 4), ('fy', f32 * 4), ('slipRatio', f32 * 4),
    ('slipAngle', f32 * 4), ('tcInAction', i32), ('absInAction', i32), ('suspensionDamage', f32 * 4),
    ('tyreTemp', f32 * 4),
], pack=4)

# ACC 1.8+: la stessa pagina continua con freni, pastiglie, cordoli (documentazione Kunos «ACC Shared Memory»)
ACC_PHYSICS = struttura('ACCPhysics', AC_PHYSICS._fields_ + [
    ('waterTemp', f32), ('brakePressure', f32 * 4), ('frontBrakeCompound', i32), ('rearBrakeCompound', i32),
    ('padLife', f32 * 4), ('discLife', f32 * 4), ('ignitionOn', i32), ('starterEngineOn', i32), ('isEngineRunning', i32),
    ('kerbVibration', f32), ('slipVibrations', f32), ('gVibrations', f32), ('absVibrations', f32),
], pack=4)

AC_GRAPHICS = struttura('ACGraphics', [      # Assetto Corsa (1.16)
    ('packetId', i32), ('status', i32), ('session', i32), ('currentTime', W(15)), ('lastTime', W(15)),
    ('bestTime', W(15)), ('split', W(15)), ('completedLaps', i32), ('position', i32), ('iCurrentTime', i32),
    ('iLastTime', i32), ('iBestTime', i32), ('sessionTimeLeft', f32), ('distanceTraveled', f32), ('isInPit', i32),
    ('currentSectorIndex', i32), ('lastSectorTime', i32), ('numberOfLaps', i32), ('tyreCompound', W(33)),
    ('replayTimeMultiplier', f32), ('normalizedCarPosition', f32), ('carCoordinates', f32 * 3),
    ('penaltyTime', f32), ('flag', i32), ('idealLineOn', i32), ('isInPitLane', i32), ('surfaceGrip', f32),
    ('mandatoryPitDone', i32), ('windSpeed', f32), ('windDirection', f32),
], pack=4)

ACC_GRAPHICS = struttura('ACCGraphics', [    # Assetto Corsa Competizione (1.8+)
    ('packetId', i32), ('status', i32), ('session', i32), ('currentTime', W(15)), ('lastTime', W(15)),
    ('bestTime', W(15)), ('split', W(15)), ('completedLaps', i32), ('position', i32), ('iCurrentTime', i32),
    ('iLastTime', i32), ('iBestTime', i32), ('sessionTimeLeft', f32), ('distanceTraveled', f32), ('isInPit', i32),
    ('currentSectorIndex', i32), ('lastSectorTime', i32), ('numberOfLaps', i32), ('tyreCompound', W(33)),
    ('replayTimeMultiplier', f32), ('normalizedCarPosition', f32), ('activeCars', i32),
    ('carCoordinates', f32 * 180), ('carID', i32 * 60), ('playerCarID', i32), ('penaltyTime', f32), ('flag', i32),
    ('penalty', i32), ('idealLineOn', i32), ('isInPitLane', i32), ('surfaceGrip', f32), ('mandatoryPitDone', i32),
    ('windSpeed', f32), ('windDirection', f32), ('isSetupMenuVisible', i32), ('mainDisplayIndex', i32),
    ('secondaryDisplayIndex', i32), ('TC', i32), ('TCCut', i32), ('EngineMap', i32), ('ABS', i32),
    ('fuelXLap', f32), ('rainLights', i32), ('flashingLights', i32), ('lightsStage', i32),
    ('exhaustTemperature', f32), ('wiperLV', i32), ('driverStintTotalTimeLeft', i32),
    ('driverStintTimeLeft', i32), ('rainTyres', i32), ('sessionIndex', i32), ('usedFuel', f32),
    ('deltaLapTime', W(15)), ('iDeltaLapTime', i32), ('estimatedLapTime', W(15)), ('iEstimatedLapTime', i32),
    ('isDeltaPositive', i32), ('iSplit', i32), ('isValidLap', i32), ('fuelEstimatedLaps', f32),
    ('trackStatus', W(33)), ('missingMandatoryPits', i32), ('Clock', f32), ('directionLightsLeft', i32),
    ('directionLightsRight', i32), ('GlobalYellow', i32), ('GlobalYellow1', i32), ('GlobalYellow2', i32),
    ('GlobalYellow3', i32), ('GlobalWhite', i32), ('GlobalGreen', i32), ('GlobalChequered', i32),
    ('GlobalRed', i32), ('mfdTyreSet', i32), ('mfdFuelToAdd', f32), ('mfdTyrePressureLF', f32),
    ('mfdTyrePressureRF', f32), ('mfdTyrePressureLR', f32), ('mfdTyrePressureRR', f32), ('trackGripStatus', i32),
    ('rainIntensity', i32), ('rainIntensityIn10min', i32), ('rainIntensityIn30min', i32),
    ('currentTyreSet', i32), ('strategyTyreSet', i32),
], pack=4)

AC_STATIC = struttura('ACStatic', [         # comune ad AC e ACC (ACC aggiunge campi in coda)
    ('smVersion', W(15)), ('acVersion', W(15)), ('numberOfSessions', i32), ('numCars', i32),
    ('carModel', W(33)), ('track', W(33)), ('playerName', W(33)), ('playerSurname', W(33)), ('playerNick', W(33)),
    ('sectorCount', i32), ('maxTorque', f32), ('maxPower', f32), ('maxRpm', i32), ('maxFuel', f32),
    ('suspensionMaxTravel', f32 * 4), ('tyreRadius', f32 * 4), ('maxTurboBoost', f32), ('deprecated_1', f32),
    ('deprecated_2', f32), ('penaltiesEnabled', i32), ('aidFuelRate', f32), ('aidTireRate', f32),
    ('aidMechanicalDamage', f32), ('aidAllowTyreBlankets', i32), ('aidStability', f32), ('aidAutoClutch', i32),
    ('aidAutoBlip', i32), ('hasDRS', i32), ('hasERS', i32), ('hasKERS', i32), ('kersMaxJ', f32),
    ('engineBrakeSettingsCount', i32), ('ersPowerControllerCount', i32), ('trackSPlineLength', f32),
    ('trackConfiguration', W(33)), ('ersMaxJ', f32), ('isTimedRace', i32), ('hasExtraLap', i32),
    ('carSkin', W(33)), ('reversedGridPositions', i32), ('pitWindowStart', i32), ('pitWindowEnd', i32),
    ('isOnline', i32), ('dryTyresName', W(33)), ('wetTyresName', W(33)),
], pack=4)

EVO_TYRE = struttura('EvoTyre', [
    ('slip', f32), ('lock', boo), ('tyre_pressure', f32), ('tyre_temperature_c', f32), ('brake_temperature_c', f32),
    ('brake_pressure', f32), ('tyre_temperature_left', f32), ('tyre_temperature_center', f32),
    ('tyre_temperature_right', f32), ('tyre_compound_front', S(33)), ('tyre_compound_rear', S(33)),
    ('tyre_normalized_pressure', f32), ('tyre_normalized_temperature_left', f32),
    ('tyre_normalized_temperature_center', f32), ('tyre_normalized_temperature_right', f32),
    ('brake_normalized_temperature', f32), ('tyre_normalized_temperature_core', f32), ('_r', C.c_byte * 128),
], pack=4)
assert C.sizeof(EVO_TYRE) == 256
def B(n): return struttura('Blocco%d' % n, [('b', i32 * (n // 4))], pack=4)   # blocchi opachi, allineati a 4

EVO_GRAPHICS = struttura('EvoGraphics', [
    ('packetId', i32), ('status', i32), ('focused_car_id_a', u64), ('focused_car_id_b', u64),
    ('player_car_id_a', u64), ('player_car_id_b', u64), ('rpm', u16), ('is_rpm_limiter_on', boo),
    ('is_change_up_rpm', boo), ('is_change_down_rpm', boo), ('tc_active', boo), ('abs_active', boo),
    ('esc_active', boo), ('launch_active', boo), ('is_ignition_on', boo), ('is_engine_running', boo),
    ('kers_is_charging', boo), ('is_wrong_way', boo), ('is_drs_available', boo), ('battery_is_charging', boo),
    ('is_max_kj_per_lap_reached', boo), ('is_max_charge_kj_per_lap_reached', boo), ('display_speed_kmh', i16),
    ('display_speed_mph', i16), ('display_speed_ms', i16), ('pitspeeding_delta', f32), ('gear_int', i16),
    ('rpm_percent', f32), ('gas_percent', f32), ('brake_percent', f32), ('handbrake_percent', f32),
    ('clutch_percent', f32), ('steering_percent', f32), ('ffb_strength', f32), ('car_ffb_multiplier', f32),
    ('water_temperature_percent', f32), ('water_pressure_bar', f32), ('fuel_pressure_bar', f32),
    ('water_temperature_c', i8), ('air_temperature_c', i8), ('oil_temperature_c', f32), ('oil_pressure_bar', f32),
    ('exhaust_temperature_c', f32), ('g_forces_x', f32), ('g_forces_y', f32), ('g_forces_z', f32),
    ('turbo_boost', f32), ('turbo_boost_level', f32), ('turbo_boost_perc', f32), ('steer_degrees', i32),
    ('current_km', f32), ('total_km', u32), ('total_driving_time_s', u32), ('time_of_day_hours', i32),
    ('time_of_day_minutes', i32), ('time_of_day_seconds', i32), ('delta_time_ms', i32),
    ('current_lap_time_ms', i32), ('predicted_lap_time_ms', i32), ('fuel_liter_current_quantity', f32),
    ('fuel_liter_current_quantity_percent', f32), ('fuel_liter_per_km', f32), ('km_per_fuel_liter', f32),
    ('current_torque', f32), ('current_bhp', i32), ('tyre_lf', EVO_TYRE), ('tyre_rf', EVO_TYRE),
    ('tyre_lr', EVO_TYRE), ('tyre_rr', EVO_TYRE), ('npos', f32), ('kers_charge_perc', f32),
    ('kers_current_perc', f32), ('control_lock_time', f32), ('car_damage', B(128)), ('car_location', i32),
    ('pit_info', B(64)), ('fuel_liter_used', f32), ('fuel_liter_per_lap', f32), ('laps_possible_with_fuel', f32),
    ('battery_temperature', f32), ('battery_voltage', f32), ('instantaneous_fuel_liter_per_km', f32),
    ('instantaneous_km_per_fuel_liter', f32), ('gear_rpm_window', f32), ('instrumentation', B(128)),
    ('instrumentation_min_limit', B(128)), ('instrumentation_max_limit', B(128)), ('electronics', B(128)),
    ('electronics_min_limit', B(128)), ('electronics_max_limit', B(128)), ('electronics_is_modifiable', B(128)),
    ('total_lap_count', i32), ('current_pos', u32), ('total_drivers', u32), ('last_laptime_ms', i32),
    ('best_laptime_ms', i32), ('flag', i32), ('global_flag', i32), ('max_gears', u32), ('engine_type', i32),
    ('has_kers', boo), ('is_last_lap', boo), ('performance_mode_name', S(33)), ('diff_coast_raw_value', f32),
    ('diff_power_raw_value', f32), ('race_cut_gained_time_ms', i32), ('distance_to_deadline', i32),
    ('race_cut_current_delta', f32), ('session_state', B(256)), ('timing_state', B(256)), ('player_ping', i32),
    ('player_latency', i32), ('player_cpu_usage', i32), ('player_cpu_usage_avg', i32), ('player_qos', i32),
    ('player_qos_avg', i32), ('player_fps', i32), ('player_fps_avg', i32), ('driver_name', S(33)),
    ('driver_surname', S(33)), ('car_model', S(33)), ('is_in_pit_box', boo), ('is_in_pit_lane', boo),
    ('is_valid_lap', boo), ('car_coordinates', f32 * 180), ('gap_ahead', f32), ('gap_behind', f32),
    ('active_cars', u8), ('fuel_per_lap', f32), ('fuel_estimated_laps', f32), ('assists_state', B(64)),
    ('max_fuel', f32), ('max_turbo_boost', f32), ('use_single_compound', boo), ('car_ids', u64 * 120),
], pack=4)

EVO_STATIC = struttura('EvoStatic', [
    ('sm_version', S(15)), ('ac_evo_version', S(15)), ('session', i32), ('session_name', S(33)), ('event_id', u8),
    ('session_id', u8), ('starting_grip', i32), ('starting_ambient_temperature_c', f32),
    ('starting_ground_temperature_c', f32), ('is_static_weather', boo), ('is_timed_race', boo), ('is_online', boo),
    ('number_of_sessions', i32), ('nation', S(33)), ('longitude', f32), ('latitude', f32), ('track', S(33)),
    ('track_configuration', S(33)), ('track_length_m', f32),
], pack=4)


# ─────────────────────────── AUTOMOBILISTA 2 (SharedMemory.h v14) ───────────────────────────
PART = struttura('AMS2Participant', [
    ('mIsActive', boo), ('mName', S(64)), ('mWorldPosition', f32 * 3), ('mCurrentLapDistance', f32),
    ('mRacePosition', u32), ('mLapsCompleted', u32), ('mCurrentLap', u32), ('mCurrentSector', i32),
])
N = 64
AMS2 = struttura('AMS2', [
    ('mVersion', u32), ('mBuildVersionNumber', u32), ('mGameState', u32), ('mSessionState', u32), ('mRaceState', u32),
    ('mViewedParticipantIndex', i32), ('mNumParticipants', i32), ('mParticipantInfo', PART * N),
    ('mUnfilteredThrottle', f32), ('mUnfilteredBrake', f32), ('mUnfilteredSteering', f32), ('mUnfilteredClutch', f32),
    ('mCarName', S(64)), ('mCarClassName', S(64)), ('mLapsInEvent', u32), ('mTrackLocation', S(64)),
    ('mTrackVariation', S(64)), ('mTrackLength', f32), ('mNumSectors', i32), ('mLapInvalidated', boo),
    ('mBestLapTime', f32), ('mLastLapTime', f32), ('mCurrentTime', f32), ('mSplitTimeAhead', f32),
    ('mSplitTimeBehind', f32), ('mSplitTime', f32), ('mEventTimeRemaining', f32), ('mPersonalFastestLapTime', f32),
    ('mWorldFastestLapTime', f32), ('mCurrentSector1Time', f32), ('mCurrentSector2Time', f32),
    ('mCurrentSector3Time', f32), ('mFastestSector1Time', f32), ('mFastestSector2Time', f32),
    ('mFastestSector3Time', f32), ('mPersonalFastestSector1Time', f32), ('mPersonalFastestSector2Time', f32),
    ('mPersonalFastestSector3Time', f32), ('mWorldFastestSector1Time', f32), ('mWorldFastestSector2Time', f32),
    ('mWorldFastestSector3Time', f32), ('mHighestFlagColour', u32), ('mHighestFlagReason', u32), ('mPitMode', u32),
    ('mPitSchedule', u32), ('mCarFlags', u32), ('mOilTempCelsius', f32), ('mOilPressureKPa', f32),
    ('mWaterTempCelsius', f32), ('mWaterPressureKPa', f32), ('mFuelPressureKPa', f32), ('mFuelLevel', f32),
    ('mFuelCapacity', f32), ('mSpeed', f32), ('mRpm', f32), ('mMaxRPM', f32), ('mBrake', f32), ('mThrottle', f32),
    ('mClutch', f32), ('mSteering', f32), ('mGear', i32), ('mNumGears', i32), ('mOdometerKM', f32),
    ('mAntiLockActive', boo), ('mLastOpponentCollisionIndex', i32), ('mLastOpponentCollisionMagnitude', f32),
    ('mBoostActive', boo), ('mBoostAmount', f32), ('mOrientation', f32 * 3), ('mLocalVelocity', f32 * 3),
    ('mWorldVelocity', f32 * 3), ('mAngularVelocity', f32 * 3), ('mLocalAcceleration', f32 * 3),
    ('mWorldAcceleration', f32 * 3), ('mExtentsCentre', f32 * 3), ('mTyreFlags', u32 * 4), ('mTerrain', u32 * 4),
    ('mTyreY', f32 * 4), ('mTyreRPS', f32 * 4), ('mTyreSlipSpeed', f32 * 4), ('mTyreTemp', f32 * 4),
    ('mTyreGrip', f32 * 4), ('mTyreHeightAboveGround', f32 * 4), ('mTyreLateralStiffness', f32 * 4),
    ('mTyreWear', f32 * 4), ('mBrakeDamage', f32 * 4), ('mSuspensionDamage', f32 * 4), ('mBrakeTempCelsius', f32 * 4),
    ('mTyreTreadTemp', f32 * 4), ('mTyreLayerTemp', f32 * 4), ('mTyreCarcassTemp', f32 * 4), ('mTyreRimTemp', f32 * 4),
    ('mTyreInternalAirTemp', f32 * 4), ('mCrashState', u32), ('mAeroDamage', f32), ('mEngineDamage', f32),
    ('mAmbientTemperature', f32), ('mTrackTemperature', f32), ('mRainDensity', f32), ('mWindSpeed', f32),
    ('mWindDirectionX', f32), ('mWindDirectionY', f32), ('mCloudBrightness', f32), ('mSequenceNumber', u32),
    ('mWheelLocalPositionY', f32 * 4), ('mSuspensionTravel', f32 * 4), ('mSuspensionVelocity', f32 * 4),
    ('mAirPressure', f32 * 4), ('mEngineSpeed', f32), ('mEngineTorque', f32), ('mWings', f32 * 2), ('mHandBrake', f32),
    ('mCurrentSector1Times', f32 * N), ('mCurrentSector2Times', f32 * N), ('mCurrentSector3Times', f32 * N),
    ('mFastestSector1Times', f32 * N), ('mFastestSector2Times', f32 * N), ('mFastestSector3Times', f32 * N),
    ('mFastestLapTimes', f32 * N), ('mLastLapTimes', f32 * N), ('mLapsInvalidated', boo * N), ('mRaceStates', u32 * N),
    ('mPitModes', u32 * N), ('mOrientations', f32 * (N * 3)), ('mSpeeds', f32 * N), ('mCarNames', S(64) * N),
    ('mCarClassNames', S(64) * N), ('mEnforcedPitStopLap', i32), ('mTranslatedTrackLocation', S(64)),
    ('mTranslatedTrackVariation', S(64)), ('mBrakeBias', f32), ('mTurboBoostPressure', f32),
    ('mTyreCompound', S(40) * 4), ('mPitSchedules', u32 * N), ('mHighestFlagColours', u32 * N),
    ('mHighestFlagReasons', u32 * N), ('mNationalities', u32 * N), ('mSnowDensity', f32), ('mSessionDuration', f32),
    ('mSessionAdditionalLaps', i32), ('mTyreTempLeft', f32 * 4), ('mTyreTempCenter', f32 * 4),
    ('mTyreTempRight', f32 * 4), ('mDrsState', u32), ('mRideHeight', f32 * 4), ('mJoyPad0', u32), ('mDPad', u32),
    ('mAntiLockSetting', i32), ('mTractionControlSetting', i32), ('mErsDeploymentMode', i32),
    ('mErsAutoModeEnabled', boo), ('mClutchTemp', f32), ('mClutchWear', f32), ('mClutchOverheated', boo),
    ('mClutchSlipping', boo), ('mYellowFlagState', i32), ('mSessionIsPrivate', boo), ('mLaunchStage', i32),
])


# ─────────────────────────── LE MANS ULTIMATE (SharedMemoryInterface.hpp) ───────────────────────────
V3 = struttura('LMUVect3', [('x', f64), ('y', f64), ('z', f64)], pack=4)
LMU_WHEEL = struttura('LMUWheel', [
    ('mSuspensionDeflection', f64), ('mRideHeight', f64), ('mSuspForce', f64), ('mBrakeTemp', f64),
    ('mBrakePressure', f64), ('mRotation', f64), ('mLateralPatchVel', f64), ('mLongitudinalPatchVel', f64),
    ('mLateralGroundVel', f64), ('mLongitudinalGroundVel', f64), ('mCamber', f64), ('mLateralForce', f64),
    ('mLongitudinalForce', f64), ('mTireLoad', f64), ('mGripFract', f64), ('mPressure', f64),
    ('mTemperature', f64 * 3), ('mWear', f64), ('mTerrainName', S(16)), ('mSurfaceType', u8), ('mFlat', boo),
    ('mDetached', boo), ('mStaticUndeflectedRadius', u8), ('mVerticalTireDeflection', f64),
    ('mWheelYLocation', f64), ('mToe', f64), ('mTireCarcassTemperature', f64),
    ('mTireInnerLayerTemperature', f64 * 3), ('mOptimalTemp', f32), ('mCompoundIndex', u8), ('mCompoundType', u8),
    ('mExpansion', u8 * 18),
], pack=4)
LMU_TELEM = struttura('LMUTelem', [
    ('mID', i32), ('mDeltaTime', f64), ('mElapsedTime', f64), ('mLapNumber', i32), ('mLapStartET', f64),
    ('mVehicleName', S(64)), ('mTrackName', S(64)), ('mPos', V3), ('mLocalVel', V3), ('mLocalAccel', V3),
    ('mOri', V3 * 3), ('mLocalRot', V3), ('mLocalRotAccel', V3), ('mGear', i32), ('mEngineRPM', f64),
    ('mEngineWaterTemp', f64), ('mEngineOilTemp', f64), ('mClutchRPM', f64), ('mUnfilteredThrottle', f64),
    ('mUnfilteredBrake', f64), ('mUnfilteredSteering', f64), ('mUnfilteredClutch', f64), ('mFilteredThrottle', f64),
    ('mFilteredBrake', f64), ('mFilteredSteering', f64), ('mFilteredClutch', f64), ('mSteeringShaftTorque', f64),
    ('mFront3rdDeflection', f64), ('mRear3rdDeflection', f64), ('mFrontWingHeight', f64), ('mFrontRideHeight', f64),
    ('mRearRideHeight', f64), ('mDrag', f64), ('mFrontDownforce', f64), ('mRearDownforce', f64), ('mFuel', f64),
    ('mEngineMaxRPM', f64), ('mScheduledStops', u8), ('mOverheating', boo), ('mDetached', boo), ('mHeadlights', boo),
    ('mDentSeverity', u8 * 8), ('mLastImpactET', f64), ('mLastImpactMagnitude', f64), ('mLastImpactPos', V3),
    ('mEngineTorque', f64), ('mCurrentSector', i32), ('mSpeedLimiter', u8), ('mMaxGears', u8),
    ('mFrontTireCompoundIndex', u8), ('mRearTireCompoundIndex', u8), ('mFuelCapacity', f64),
    ('mFrontFlapActivated', u8), ('mRearFlapActivated', u8), ('mRearFlapLegalStatus', u8), ('mIgnitionStarter', u8),
    ('mFrontTireCompoundName', S(18)), ('mRearTireCompoundName', S(18)), ('mSpeedLimiterAvailable', u8),
    ('mAntiStallActivated', u8), ('mUnused', u8 * 2), ('mVisualSteeringWheelRange', f32), ('mRearBrakeBias', f64),
    ('mTurboBoostPressure', f64), ('mPhysicsToGraphicsOffset', f32 * 3), ('mPhysicalSteeringWheelRange', f32),
    ('mDeltaBest', f64), ('mBatteryChargeFraction', f64), ('mElectricBoostMotorTorque', f64),
    ('mElectricBoostMotorRPM', f64), ('mElectricBoostMotorTemperature', f64), ('mElectricBoostWaterTemperature', f64),
    ('mElectricBoostMotorState', u8), ('mLapInvalidated', boo), ('mABSActive', boo), ('mTCActive', boo),
    ('mSpeedLimiterActive', boo), ('mWiperState', u8), ('mTC', u8), ('mTCMax', u8), ('mTCSlip', u8),
    ('mTCSlipMax', u8), ('mTCCut', u8), ('mTCCutMax', u8), ('mABS', u8), ('mABSMax', u8), ('mMotorMap', u8),
    ('mMotorMapMax', u8), ('mMigration', u8), ('mMigrationMax', u8), ('mFrontAntiSway', u8),
    ('mFrontAntiSwayMax', u8), ('mRearAntiSway', u8), ('mRearAntiSwayMax', u8), ('mLiftAndCoastProgress', u8),
    ('mTrackLimitsSteps', u8), ('mRegen', f32), ('mStateOfCharge', f32), ('mVirtualEnergy', f32),
    ('mTimeGapCarAhead', f32), ('mTimeGapCarBehind', f32), ('mTimeGapPlaceAhead', f32), ('mTimeGapPlaceBehind', f32),
    ('mVehicleModel', S(30)), ('mVehicleClass', u8), ('mVehicleChampionship', u8), ('mExpansion', u8 * 20),
    ('mWheels', LMU_WHEEL * 4),
], pack=4)
LMU_VSCOR = struttura('LMUVehScoring', [
    ('mID', i32), ('mDriverName', S(32)), ('mVehicleName', S(64)), ('mTotalLaps', i16), ('mSector', i8),
    ('mFinishStatus', i8), ('mLapDist', f64), ('mPathLateral', f64), ('mTrackEdge', f64), ('mBestSector1', f64),
    ('mBestSector2', f64), ('mBestLapTime', f64), ('mLastSector1', f64), ('mLastSector2', f64), ('mLastLapTime', f64),
    ('mCurSector1', f64), ('mCurSector2', f64), ('mNumPitstops', i16), ('mNumPenalties', i16), ('mIsPlayer', boo),
    ('mControl', i8), ('mInPits', boo), ('mPlace', u8), ('mVehicleClass', S(32)), ('mTimeBehindNext', f64),
    ('mLapsBehindNext', i32), ('mTimeBehindLeader', f64), ('mLapsBehindLeader', i32), ('mLapStartET', f64),
    ('mPos', V3), ('mLocalVel', V3), ('mLocalAccel', V3), ('mOri', V3 * 3), ('mLocalRot', V3), ('mLocalRotAccel', V3),
    ('mHeadlights', u8), ('mPitState', u8), ('mServerScored', u8), ('mIndividualPhase', u8), ('mQualification', i32),
    ('mTimeIntoLap', f64), ('mEstimatedLapTime', f64), ('mPitGroup', S(24)), ('mFlag', u8), ('mUnderYellow', boo),
    ('mCountLapFlag', u8), ('mInGarageStall', boo), ('mUpgradePack', u8 * 16), ('mPitLapDist', f32),
    ('mBestLapSector1', f32), ('mBestLapSector2', f32), ('mSteamID', u64), ('mVehFilename', S(32)),
    ('mAttackMode', i16), ('mFuelFraction', u8), ('mDRSState', boo), ('mExpansion', u8 * 4),
], pack=4)
LMU_SINFO = struttura('LMUScoringInfo', [
    ('mTrackName', S(64)), ('mSession', i32), ('mCurrentET', f64), ('mEndET', f64), ('mMaxLaps', i32),
    ('mLapDist', f64), ('mResultsStreamPointer', u8 * 8), ('mNumVehicles', i32), ('mGamePhase', u8),
    ('mYellowFlagState', C.c_char), ('mSectorFlag', u8 * 3), ('mStartLight', u8), ('mNumRedLights', u8),
    ('mInRealtime', boo), ('mPlayerName', S(32)), ('mPlrFileName', S(64)), ('mDarkCloud', f64), ('mRaining', f64),
    ('mAmbientTemp', f64), ('mTrackTemp', f64), ('mWind', V3), ('mMinPathWetness', f64), ('mMaxPathWetness', f64),
    ('mGameMode', u8), ('mIsPasswordProtected', boo), ('mServerPort', u16), ('mServerPublicIP', u32),
    ('mMaxPlayers', i32), ('mServerName', S(32)), ('mStartET', f32), ('mAvgPathWetness', f64),
    ('mSessionTimeRemaining', f32), ('mTimeOfDay', f32), ('mIsFixedSetup', boo), ('mTrackGripLevel', u8),
    ('mCloudCoverage', u8), ('mTrackLimitsStepsPerPenalty', u8), ('mTrackLimitsStepsPerPoint', u8),
    ('mExpansion', u8 * 187), ('mVehiclePointer', u8 * 8),
], pack=4)
LMU_APP = struttura('LMUApp', [('mAppWindow', u64), ('mWidth', u32), ('mHeight', u32), ('mRefreshRate', u32),
                               ('mWindowed', u32), ('mOptionsLocation', u8), ('mOptionsPage', S(31)),
                               ('mExpansion', u8 * 204)], pack=4)
LMU_GENERIC = struttura('LMUGeneric', [('events', u32 * 16), ('gameVersion', i32), ('FFBTorque', f32),
                                       ('appInfo', LMU_APP)], pack=4)
LMU_PATHS = struttura('LMUPaths', [('p', S(260) * 5)], pack=4)
LMU_SCORING = struttura('LMUScoring', [('scoringInfo', LMU_SINFO), ('scoringStreamSize', u8 * 12),
                                       ('vehScoringInfo', LMU_VSCOR * 104), ('scoringStream', S(65536))], pack=4)
LMU_TELEMETRY = struttura('LMUTelemetry', [('activeVehicles', u8), ('playerVehicleIdx', u8), ('playerHasVehicle', boo),
                                           ('telemInfo', LMU_TELEM * 104)], pack=4)
LMU = struttura('LMUObjectOut', [('generic', LMU_GENERIC), ('paths', LMU_PATHS), ('scoring', LMU_SCORING),
                                 ('telemetry', LMU_TELEMETRY)], pack=4)


# ─────────────────────────── rFACTOR 2 (plugin rF2SharedMemoryMapPlugin) ───────────────────────────
def rf2():
    """Le strutture del plugin: riprese da rF2data.py (generato da rF2data.cs)."""
    import importlib.util, os
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'riferimenti', 'rF2data.py')
    spec = importlib.util.spec_from_file_location('rF2data', p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m
