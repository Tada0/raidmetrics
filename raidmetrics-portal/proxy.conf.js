const apiUrl = process.env['API_URL'];
const frontendSecret = process.env['FRONTEND_SECRET'];

module.exports = {
  '/api': {
    target: apiUrl,
    secure: false,
    changeOrigin: true,
    headers: {
      'X-Frontend-Auth': frontendSecret,
    },
  },
};
