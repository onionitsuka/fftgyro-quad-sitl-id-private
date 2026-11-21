/* Application adapter linking the unmodified official Hakoniwa static libraries.
 * NED / FRD, SI. Hakoniwa calculates gravity/Coriolis and rigid-body rotation;
 * arbitrary body Fx/Fy/Fz are added here because its C translation API takes T only.
 */
#include "physics/drone_physics_c.h"
void hako_wrench_acceleration(const double *velocity_body, const double *euler,
    const double *rate, const double *wrench, double mass, const double *inertia,
    double gravity, double *acceleration_world, double *angular_acceleration) {
    dp_vector_t v={velocity_body[0],velocity_body[1],velocity_body[2]};
    dp_euler_t e={euler[0],euler[1],euler[2]};
    dp_vector_t w={rate[0],rate[1],rate[2]};
    dp_vector_t m={wrench[3],wrench[4],wrench[5]};
    dp_vector_t a=dp_acceleration_in_body_frame(&v,&e,&w,0.,mass,gravity,0.);
    /* Body velocity derivative -> inertial acceleration expressed in body. */
    a.x += wrench[0]/mass + w.y*v.z-w.z*v.y;
    a.y += wrench[1]/mass + w.z*v.x-w.x*v.z;
    a.z += wrench[2]/mass + w.x*v.y-w.y*v.x;
    dp_vector_t world=dp_ground_vector_from_body(&a,&e);
    dp_vector_t alpha=dp_angular_acceleration_in_body_frame(&w,&m,inertia[0],inertia[1],inertia[2]);
    acceleration_world[0]=world.x; acceleration_world[1]=world.y; acceleration_world[2]=world.z;
    angular_acceleration[0]=alpha.x; angular_acceleration[1]=alpha.y; angular_acceleration[2]=alpha.z;
}
