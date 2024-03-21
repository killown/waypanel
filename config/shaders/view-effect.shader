#version 100
@builtin_ext@
@builtin@

precision mediump float;

varying mediump vec2 uvpos;

void main() {
    // Set the shadow color (black) and opacity (50%)
    vec4 shadowColor = vec4(0.0, 0.0, 0.0, 0.8);

    // Output the shadow color
    gl_FragColor = shadowColor;
}

