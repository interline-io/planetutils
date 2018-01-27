set +e
: ${PLANET_OSM_BUCKET?"Need to set PLANET_OSM_BUCKET"}

PLANET_URL="https://planet.openstreetmap.org/pbf/planet-latest.osm.pbf"

# Get all planets
echo "getting planets in s3://${PLANET_OSM_BUCKET}"
s3files=$(aws s3 ls s3://${PLANET_OSM_BUCKET} | grep 'planet-' | awk '{print $4}' | sort -r)
planets=($s3files)
# Latest planet
latest=${planets[0]}
# Keep 4 latest planets
remove=${planets[@]:4}

if [ -z "$latest" ]
then
  echo "downloading latest planet from ${PLANET_URL}"
  echo "test" > planet-latest.osm.pbf
  # curl -s -o planet-latest.osm.pbf ${PLANET_URL}
else
  echo "downloading s3://${PLANET_OSM_BUCKET}/${latest}"
  aws s3 cp s3://${PLANET_OSM_BUCKET}/${latest} planet-latest.osm.pbf
fi

# Download current planet and create new planet
today=$(date -u +%Y-%m-%dT%H:%m:%S)
updated="planet-${today}.osm.pbf"
echo "osmupdate"
echo "test" > ${updated}
# osmupdate --verbose --day --hour planet-latest.osm.pbf ${updated}

# Upload new planet
echo "uploading to s3://${PLANET_OSM_BUCKET}/${updated}"
aws s3 cp ${updated} s3://${PLANET_OSM_BUCKET}

# Remove old files
for i in "${remove[@]}"
do
  echo "removing ${i}"
  aws s3 rm s3://${PLANET_OSM_BUCKET}/${i}
done

echo "done"
