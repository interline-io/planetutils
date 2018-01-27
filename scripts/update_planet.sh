set +e
: ${PLANET_OSM_BUCKET?"Need to set PLANET_OSM_BUCKET"}
echo "Updating planet"

# Get all planets
s3files=$(aws s3 ls s3://${PLANET_OSM_BUCKET} | grep 'planet-' | awk '{print $4}' | sort -r)
planets=($s3files)
# Latest planet
latest=${planets[0]}
# Keep 4 latest planets
remove=${planets[@]:4}

# Download current planet and create new planet
today=$(date -u +%Y-%m-%dT%H:%m:%S)
updated="planet-${today}.osm.pbf"
echo "  downloading s3://${PLANET_OSM_BUCKET}/${latest}"
aws s3 cp s3://${PLANET_OSM_BUCKET}/${latest} planet-latest.osm.pbf
echo "  osmupdate"
echo "test" > ${updated}
# osmupdate --verbose --day --hour planet-latest.osm.pbf ${updated}

# Upload new planet
echo "  uploading to s3://${PLANET_OSM_BUCKET}/${updated}"
aws s3 cp ${updated} s3://${PLANET_OSM_BUCKET}

# Remove old files
for i in "${remove[@]}"
do
  echo "  removing ${i}"
  aws s3 rm s3://${PLANET_OSM_BUCKET}/${i}
done

echo "  done"
