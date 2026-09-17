% One frame from a FLIR camera into MATLAB through the spinnaker_ctypes Python package.
% Needs MATLAB R2022a or newer and a Python with `pip install flir-spinnaker-linux`.
pyenv(Version="/usr/bin/python3");
cam = py.spinnaker_ctypes.Camera();
cam.configure(pyargs('exposure_us', 5000, 'pixel_format', 'Mono8'));
img = uint8(cam.grab());
cam.close();
figure; imagesc(img); axis image; colormap gray; title(sprintf('%dx%d, mean %.1f', size(img, 2), size(img, 1), mean(img(:))));
