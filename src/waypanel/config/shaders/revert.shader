#version 100
@builtin_ext@
@builtin@

precision mediump float;

varying mediump vec2 uvpos;

void main()
{
    vec4 c = get_pixel(uvpos);
    gl_FragColor = c;
}